from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN, ROLE_RECEPTIONIST
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.user import User
from app.db.session import get_db
from app.main import app
from app.api.v1.endpoints.ringcentral_live import call_center_stream
from app.services.call_center_bus import call_center_event_bus
from app.services.integration_tokens import decrypt_token, encrypt_token
from app.services.ringcentral_realtime import (
    RingCentralRealtimeError,
    load_ringcentral_runtime_config,
    make_state,
    parse_state,
    validate_ringcentral_startup_configuration,
)


def _set_required_env(monkeypatch) -> None:
    monkeypatch.setenv("RINGCENTRAL_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("RINGCENTRAL_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("RINGCENTRAL_SERVER_URL", "https://platform.ringcentral.com")
    monkeypatch.setenv(
        "RINGCENTRAL_REDIRECT_URI",
        "https://api.360-encompass.com/api/v1/integrations/ringcentral/callback",
    )
    monkeypatch.setenv("RINGCENTRAL_WEBHOOK_SHARED_SECRET", "webhook-secret-value")
    monkeypatch.setenv("PUBLIC_WEBHOOK_BASE_URL", "https://api.360-encompass.com")
    monkeypatch.setenv("INTEGRATION_TOKEN_KEY", "integration-token-key-for-tests")


def _build_session(tmp_path):
    database_file = tmp_path / "ringcentral_realtime.sqlite"
    engine = create_engine(
        f"sqlite:///{database_file}",
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    from app.db import models as _models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return engine, testing_session_local


def _create_user_membership(session_factory, *, org_name: str, email: str, role: str) -> tuple[str, str, str]:
    with session_factory() as db:
        org = Organization(name=org_name)
        db.add(org)
        db.flush()

        user = User(
            email=email,
            full_name=email.split("@", 1)[0],
            hashed_password=hash_password("AdminPass123!"),
            is_active=True,
        )
        db.add(user)
        db.flush()

        db.add(
            OrganizationMembership(
                organization_id=org.id,
                user_id=user.id,
                role=role,
            )
        )
        db.commit()
        return create_access_token({"sub": user.id, "org_id": org.id}), org.id, user.id


def test_ringcentral_state_signing_and_verification(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    config = load_ringcentral_runtime_config()

    state = make_state(
        config=config,
        organization_id="org-123",
        user_id="user-456",
        return_to="https://360-encompass.com/admin-center",
    )
    parsed = parse_state(config=config, state=state)
    assert parsed.organization_id == "org-123"
    assert parsed.user_id == "user-456"
    assert parsed.return_to == "https://360-encompass.com/admin-center"

    header_part, payload_part, signature_part = state.split(".")
    tampered_payload_part = ("A" if payload_part[:1] != "A" else "B") + payload_part[1:]
    bad_state = ".".join([header_part, tampered_payload_part, signature_part])
    try:
        parse_state(config=config, state=bad_state)
    except RingCentralRealtimeError as exc:
        assert exc.detail == "invalid_state_signature"
    else:
        raise AssertionError("Expected invalid state signature error")


def test_ringcentral_token_encrypt_decrypt_roundtrip(monkeypatch) -> None:
    monkeypatch.setenv("INTEGRATION_TOKEN_KEY", "integration-token-key-for-tests")
    raw_token = "ringcentral-refresh-token-value"
    encrypted = encrypt_token(raw_token, key_env="INTEGRATION_TOKEN_KEY")
    assert encrypted != raw_token
    assert decrypt_token(encrypted, key_env="INTEGRATION_TOKEN_KEY") == raw_token


def test_ringcentral_startup_validation_fails_when_required_env_missing(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.delenv("RINGCENTRAL_CLIENT_ID", raising=False)
    try:
        validate_ringcentral_startup_configuration()
    except RingCentralRealtimeError as exc:
        assert exc.detail == "RINGCENTRAL_CLIENT_ID is not configured"
    else:
        raise AssertionError("Expected startup configuration validation failure")


def test_ringcentral_webhook_pushes_event_to_bus(tmp_path, monkeypatch) -> None:
    _set_required_env(monkeypatch)
    engine, session_factory = _build_session(tmp_path)
    try:
        _admin_token, org_id, _user_id = _create_user_membership(
            session_factory,
            org_name="RingCentral SSE Org",
            email="ringcentral-admin-sse@example.com",
            role=ROLE_ADMIN,
        )
        webhook_payload = {
            "event": "/restapi/v1.0/account/~/extension/~/telephony/sessions",
            "eventId": "evt-stream-1",
            "body": {
                "telephonySessionId": "session-stream-1",
                "id": "call-stream-1",
                "from": {"phoneNumber": "+15550001111"},
                "to": {"phoneNumber": "+15550002222"},
                "direction": "Inbound",
                "status": {"code": "Ringing"},
            },
        }

        listener_id, queue = asyncio.run(call_center_event_bus.subscribe(org_id))
        try:
            with TestClient(app) as client:
                ingest = client.post(
                    f"/api/v1/integrations/ringcentral/webhook?organization_id={org_id}&secret=webhook-secret-value",
                    json=webhook_payload,
                )
                assert ingest.status_code == 200
            item = asyncio.run(asyncio.wait_for(queue.get(), timeout=2.0))
            assert item["event"] == "call"
            assert item["data"]["call_id"] == "call-stream-1"
        finally:
            asyncio.run(call_center_event_bus.unsubscribe(org_id, listener_id))
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_ringcentral_test_event_publishes_call_and_presence(tmp_path, monkeypatch) -> None:
    _set_required_env(monkeypatch)
    engine, session_factory = _build_session(tmp_path)
    try:
        admin_token, org_id, _user_id = _create_user_membership(
            session_factory,
            org_name="RingCentral Test Event Org",
            email="ringcentral-test-event-admin@example.com",
            role=ROLE_ADMIN,
        )

        listener_id, queue = asyncio.run(call_center_event_bus.subscribe(org_id))
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/v1/webhooks/ringcentral/test-event",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
                assert response.status_code == 200
                assert response.json() == {"ok": True}

            first = asyncio.run(asyncio.wait_for(queue.get(), timeout=2.0))
            second = asyncio.run(asyncio.wait_for(queue.get(), timeout=2.0))
            events = {str(first.get("event")), str(second.get("event"))}
            assert events == {"call", "presence"}
            assert first["data"]["organization_id"] == org_id
            assert second["data"]["organization_id"] == org_id
        finally:
            asyncio.run(call_center_event_bus.unsubscribe(org_id, listener_id))
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_call_center_sse_stream_emits_event(tmp_path, monkeypatch) -> None:
    _set_required_env(monkeypatch)
    engine, session_factory = _build_session(tmp_path)
    try:
        stream_token, _org_id, _user_id = _create_user_membership(
            session_factory,
            org_name="RingCentral Stream Org",
            email="ringcentral-stream-reception@example.com",
            role=ROLE_RECEPTIONIST,
        )

        async def fake_subscribe(_organization_id: str):
            queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
            await queue.put({"event": "call", "data": {"call_id": "prefed-call", "state": "ringing"}})
            return "listener-test", queue

        async def fake_unsubscribe(_organization_id: str, _listener_id: str):
            return None

        monkeypatch.setattr("app.api.v1.endpoints.ringcentral_live.call_center_event_bus.subscribe", fake_subscribe)
        monkeypatch.setattr("app.api.v1.endpoints.ringcentral_live.call_center_event_bus.unsubscribe", fake_unsubscribe)

        class FakeRequest:
            def __init__(self) -> None:
                self._calls = 0

            async def is_disconnected(self) -> bool:
                self._calls += 1
                return self._calls > 1

        with session_factory() as db:
            response = asyncio.run(
                call_center_stream(
                    request=FakeRequest(),
                    access_token=stream_token,
                    credentials=None,
                    db=db,
                )
            )
            chunk = asyncio.run(response.body_iterator.__anext__())
            chunk_text = chunk.decode() if isinstance(chunk, bytes) else str(chunk)
            assert "event: call" in chunk_text
            assert "prefed-call" in chunk_text
            asyncio.run(response.body_iterator.aclose())
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
