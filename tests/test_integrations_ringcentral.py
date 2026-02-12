from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN, ROLE_RECEPTIONIST
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.models.audit_event import AuditEvent
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.ringcentral_credential import RingCentralCredential
from app.db.models.ringcentral_subscription import RingCentralSubscription
from app.db.models.user import User
from app.db.session import get_db
from app.main import app


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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
    monkeypatch.setenv("RINGCENTRAL_POST_CONNECT_REDIRECT", "https://360-encompass.com/admin-center")


def _build_session(tmp_path):
    database_file = tmp_path / "integrations_ringcentral.sqlite"
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


def test_ringcentral_status_returns_false_when_not_connected(tmp_path, monkeypatch) -> None:
    _set_required_env(monkeypatch)
    engine, session_factory = _build_session(tmp_path)
    try:
        admin_token, _org_id, _user_id = _create_user_membership(
            session_factory,
            org_name="RingCentral Status Org",
            email="ringcentral-status-admin@example.com",
            role=ROLE_ADMIN,
        )
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/integrations/ringcentral/status",
                headers=_auth_header(admin_token),
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["connected"] is False
            assert payload["account_id"] is None
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_ringcentral_connect_requires_permissions(tmp_path, monkeypatch) -> None:
    _set_required_env(monkeypatch)
    engine, session_factory = _build_session(tmp_path)
    try:
        receptionist_token, _org_id, _user_id = _create_user_membership(
            session_factory,
            org_name="RingCentral Permission Org",
            email="ringcentral-reception@example.com",
            role=ROLE_RECEPTIONIST,
        )
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/integrations/ringcentral/connect",
                headers=_auth_header(receptionist_token),
            )
            assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_ringcentral_connect_get_redirects_to_authorize(tmp_path, monkeypatch) -> None:
    _set_required_env(monkeypatch)
    engine, session_factory = _build_session(tmp_path)
    try:
        admin_token, _org_id, _user_id = _create_user_membership(
            session_factory,
            org_name="RingCentral Redirect Org",
            email="ringcentral-redirect-admin@example.com",
            role=ROLE_ADMIN,
        )
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/integrations/ringcentral/connect?access_token={admin_token}",
                follow_redirects=False,
            )
            assert response.status_code == 303
            location = response.headers["location"]
            assert location.startswith("https://platform.ringcentral.com/restapi/oauth/authorize?")
            parsed_query = parse_qs(urlparse(location).query)
            assert parsed_query.get("state")
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_ringcentral_callback_stores_encrypted_tokens(tmp_path, monkeypatch) -> None:
    _set_required_env(monkeypatch)
    engine, session_factory = _build_session(tmp_path)
    try:
        admin_token, org_id, user_id = _create_user_membership(
            session_factory,
            org_name="RingCentral Callback Org",
            email="ringcentral-callback-admin@example.com",
            role=ROLE_ADMIN,
        )

        class FakeTokenResponse:
            status_code = 200

            def json(self):
                return {
                    "access_token": "access-token-plain",
                    "refresh_token": "refresh-token-plain",
                    "expires_in": 3600,
                    "scope": "ReadAccounts ReadCallLog",
                }

        class FakeProfileResponse:
            status_code = 200

            def json(self):
                return {"id": "ext-123", "accountId": "acct-456"}

        def fake_post(url, data=None, auth=None, timeout=None):  # noqa: ANN001
            assert url == "https://platform.ringcentral.com/restapi/oauth/token"
            assert data["grant_type"] == "authorization_code"
            assert data["code"] == "valid-code"
            assert auth == ("test-client-id", "test-client-secret")
            assert timeout == 20.0
            return FakeTokenResponse()

        def fake_get(url, headers=None, timeout=None):  # noqa: ANN001
            assert url == "https://platform.ringcentral.com/restapi/v1.0/account/~/extension/~"
            assert headers == {"Authorization": "Bearer access-token-plain"}
            assert timeout == 20.0
            return FakeProfileResponse()

        monkeypatch.setattr("app.services.ringcentral_realtime.httpx.post", fake_post)
        monkeypatch.setattr("app.services.ringcentral_realtime.httpx.get", fake_get)
        monkeypatch.setattr(
            "app.api.v1.endpoints.ringcentral_live.ensure_subscription",
            lambda **kwargs: SimpleNamespace(status="ACTIVE", rc_subscription_id="sub-1", expires_at=None),
        )

        with TestClient(app) as client:
            connect_response = client.post(
                "/api/v1/integrations/ringcentral/connect",
                headers=_auth_header(admin_token),
            )
            assert connect_response.status_code == 200
            auth_url = connect_response.json()["authorization_url"]
            parsed_query = parse_qs(urlparse(auth_url).query)
            state = parsed_query["state"][0]

            callback_response = client.get(
                "/api/v1/integrations/ringcentral/callback",
                params={"code": "valid-code", "state": state},
                follow_redirects=False,
            )
            assert callback_response.status_code == 303
            callback_target = callback_response.headers["location"]
            parsed_target = parse_qs(urlparse(callback_target).query)
            assert parsed_target["connected"] == ["1"]
            assert "err" not in parsed_target

        with session_factory() as db:
            row = db.execute(
                select(RingCentralCredential).where(
                    RingCentralCredential.organization_id == org_id,
                    RingCentralCredential.user_id == user_id,
                )
            ).scalar_one_or_none()
            assert row is not None
            assert row.rc_account_id == "acct-456"
            assert row.rc_extension_id == "ext-123"
            assert row.scopes == "ReadAccounts ReadCallLog"
            assert row.access_token_enc != "access-token-plain"
            assert row.refresh_token_enc != "refresh-token-plain"

            audit_event = db.execute(
                select(AuditEvent).where(AuditEvent.action == "integration.ringcentral.connected")
            ).scalar_one_or_none()
            assert audit_event is not None
            assert audit_event.organization_id == org_id
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_ringcentral_callback_error_redirects_with_connected_zero(tmp_path, monkeypatch) -> None:
    _set_required_env(monkeypatch)
    engine, session_factory = _build_session(tmp_path)
    try:
        _admin_token, _org_id, _user_id = _create_user_membership(
            session_factory,
            org_name="RingCentral Callback Error Org",
            email="ringcentral-callback-error-admin@example.com",
            role=ROLE_ADMIN,
        )
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/integrations/ringcentral/callback",
                params={"error": "access_denied"},
                follow_redirects=False,
            )
            assert response.status_code == 303
            target = response.headers["location"]
            parsed_target = parse_qs(urlparse(target).query)
            assert parsed_target["connected"] == ["0"]
            assert parsed_target["err"] == ["access_denied"]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_ringcentral_ensure_subscription_creates_and_persists(tmp_path, monkeypatch) -> None:
    _set_required_env(monkeypatch)
    engine, session_factory = _build_session(tmp_path)
    try:
        admin_token, org_id, user_id = _create_user_membership(
            session_factory,
            org_name="RingCentral Subscription Org",
            email="ringcentral-subscription-admin@example.com",
            role=ROLE_ADMIN,
        )

        expiry = datetime.now(timezone.utc) + timedelta(days=2)

        monkeypatch.setattr(
            "app.services.ringcentral_realtime.get_valid_access_token",
            lambda **kwargs: ("access-token-value", SimpleNamespace()),
        )
        monkeypatch.setattr(
            "app.services.ringcentral_realtime.create_subscription",
            lambda **kwargs: ("sub-created-123", expiry),
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/integrations/ringcentral/ensure-subscription",
                headers=_auth_header(admin_token),
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == "ACTIVE"
            assert payload["rc_subscription_id"] == "sub-created-123"

        with session_factory() as db:
            row = db.execute(
                select(RingCentralSubscription).where(
                    RingCentralSubscription.organization_id == org_id,
                    RingCentralSubscription.user_id == user_id,
                )
            ).scalar_one_or_none()
            assert row is not None
            assert row.status == "ACTIVE"
            assert row.rc_subscription_id == "sub-created-123"
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_ringcentral_status_is_org_scoped(tmp_path, monkeypatch) -> None:
    _set_required_env(monkeypatch)
    engine, session_factory = _build_session(tmp_path)
    try:
        admin_a_token, org_a_id, user_a_id = _create_user_membership(
            session_factory,
            org_name="RingCentral Org A",
            email="ringcentral-admin-a@example.com",
            role=ROLE_ADMIN,
        )
        admin_b_token, org_b_id, user_b_id = _create_user_membership(
            session_factory,
            org_name="RingCentral Org B",
            email="ringcentral-admin-b@example.com",
            role=ROLE_ADMIN,
        )

        with session_factory() as db:
            db.add(
                RingCentralCredential(
                    organization_id=org_a_id,
                    user_id=user_a_id,
                    rc_account_id="acct-a",
                    rc_extension_id="ext-a",
                    access_token_enc="encrypted-access",
                    refresh_token_enc="encrypted-refresh",
                    token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                    scopes="ReadAccounts",
                )
            )
            db.commit()

        with TestClient(app) as client:
            org_a = client.get(
                "/api/v1/integrations/ringcentral/status",
                headers=_auth_header(admin_a_token),
            )
            assert org_a.status_code == 200
            assert org_a.json()["connected"] is True

            org_b = client.get(
                "/api/v1/integrations/ringcentral/status",
                headers=_auth_header(admin_b_token),
            )
            assert org_b.status_code == 200
            payload_b = org_b.json()
            assert payload_b["connected"] is False
            assert payload_b["account_id"] is None
            assert user_a_id != user_b_id
            assert org_b_id != org_a_id
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
