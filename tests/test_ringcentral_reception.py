from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_RECEPTIONIST
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.models.integration_token import IntegrationToken
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.reception_call_workflow import ReceptionCallWorkflow
from app.db.models.ringcentral_event import RingCentralEvent
from app.db.models.task import Task
from app.db.models.user import User
from app.db.session import get_db
from app.main import app


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _build_session(tmp_path):
    database_file = tmp_path / "ringcentral_reception.sqlite"
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


def _seed_reception_user(session_factory) -> tuple[str, str]:
    with session_factory() as db:
        org = Organization(name="RingCentral Reception Org")
        db.add(org)
        db.flush()

        user = User(
            email="reception-workflow@example.com",
            full_name="Reception Workflow",
            hashed_password=hash_password("ReceptionPass123!"),
            is_active=True,
        )
        db.add(user)
        db.flush()

        db.add(
            OrganizationMembership(
                organization_id=org.id,
                user_id=user.id,
                role=ROLE_RECEPTIONIST,
            )
        )
        db.add(
            IntegrationToken(
                organization_id=org.id,
                provider="ringcentral",
                access_token_enc="encrypted-access",
                refresh_token_enc="encrypted-refresh",
                account_id="acct-123",
                extension_id="ext-123",
            )
        )
        db.commit()
        return create_access_token({"sub": user.id, "org_id": org.id}), org.id


def test_ringcentral_webhook_and_reception_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RINGCENTRAL_WEBHOOK_SECRET", "webhook-secret-value")
    engine, session_factory = _build_session(tmp_path)
    try:
        receptionist_token, org_id = _seed_reception_user(session_factory)
        webhook_payload = {
            "event": "/restapi/v1.0/account/~/extension/~/telephony/sessions",
            "eventId": "evt-001",
            "body": {
                "telephonySessionId": "session-abc",
                "id": "call-abc",
                "from": {"phoneNumber": "+15550001111"},
                "to": {"phoneNumber": "+15550002222"},
                "direction": "Inbound",
                "status": {"code": "Missed"},
                "startTime": "2026-02-11T12:30:00Z",
                "endTime": "2026-02-11T12:31:00Z",
                "accountId": "acct-123",
            },
        }

        with TestClient(app) as client:
            webhook_response = client.post(
                f"/api/v1/integrations/ringcentral/webhook?organization_id={org_id}&secret=webhook-secret-value",
                json=webhook_payload,
            )
            assert webhook_response.status_code == 200
            event_id = webhook_response.json()["event_id"]

            calls_response = client.get(
                "/api/v1/reception/calls",
                headers=_auth_header(receptionist_token),
            )
            assert calls_response.status_code == 200
            calls = calls_response.json()
            assert len(calls) == 1
            assert calls[0]["id"] == event_id
            assert calls[0]["disposition"].lower() == "missed"

            workflow_response = client.patch(
                f"/api/v1/reception/calls/{event_id}/workflow",
                json={
                    "workflow_status": "callback_attempted",
                    "note": "Left callback voicemail.",
                },
                headers=_auth_header(receptionist_token),
            )
            assert workflow_response.status_code == 200
            workflow_payload = workflow_response.json()
            assert workflow_payload["workflow_status"] == "callback_attempted"
            assert workflow_payload["ringcentral_event_id"] == event_id

            followup_response = client.post(
                f"/api/v1/reception/calls/{event_id}/followup",
                json={"note": "Create callback follow-up task"},
                headers=_auth_header(receptionist_token),
            )
            assert followup_response.status_code == 200
            followup_payload = followup_response.json()
            assert followup_payload["ringcentral_event_id"] == event_id
            assert followup_payload["task_id"]

            presence_response = client.get(
                "/api/v1/reception/presence",
                headers=_auth_header(receptionist_token),
            )
            assert presence_response.status_code == 200
            assert presence_response.json()["items"]

        with session_factory() as db:
            stored_event = db.execute(
                select(RingCentralEvent).where(RingCentralEvent.organization_id == org_id)
            ).scalar_one_or_none()
            assert stored_event is not None
            assert stored_event.call_id == "call-abc"

            stored_workflow = db.execute(
                select(ReceptionCallWorkflow).where(
                    ReceptionCallWorkflow.organization_id == org_id,
                    ReceptionCallWorkflow.ringcentral_event_id == stored_event.id,
                )
            ).scalar_one_or_none()
            assert stored_workflow is not None
            assert stored_workflow.followup_task_id is not None

            followup_task = db.execute(
                select(Task).where(Task.id == stored_workflow.followup_task_id)
            ).scalar_one_or_none()
            assert followup_task is not None
            assert followup_task.related_type == "call"
            assert followup_task.related_id == stored_event.id
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_ringcentral_webhook_resolves_org_without_query_param(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RINGCENTRAL_WEBHOOK_SECRET", "webhook-secret-value")
    engine, session_factory = _build_session(tmp_path)
    try:
        _receptionist_token, org_id = _seed_reception_user(session_factory)
        webhook_payload = {
            "event": "/restapi/v1.0/account/~/extension/~/telephony/sessions",
            "eventId": "evt-002",
            "body": {
                "telephonySessionId": "session-def",
                "id": "call-def",
                "from": {"phoneNumber": "+15550003333"},
                "to": {"phoneNumber": "+15550004444"},
                "direction": "Inbound",
                "status": {"code": "Missed"},
                "accountId": "acct-123",
            },
        }

        with TestClient(app) as client:
            webhook_response = client.post(
                "/api/v1/integrations/ringcentral/webhook?secret=webhook-secret-value",
                json=webhook_payload,
            )
            assert webhook_response.status_code == 200
            event_id = webhook_response.json()["event_id"]

        with session_factory() as db:
            stored_event = db.execute(
                select(RingCentralEvent).where(RingCentralEvent.id == event_id)
            ).scalar_one_or_none()
            assert stored_event is not None
            assert stored_event.organization_id == org_id
            assert stored_event.call_id == "call-def"
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
