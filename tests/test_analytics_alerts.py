from __future__ import annotations

import datetime as dt
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN, ROLE_RECEPTIONIST
from app.core.security import create_access_token
from app.db.base import Base
from app.db.models.analytics_alert import AnalyticsAlert
from app.db.models.audit_event import AuditEvent
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.user import User
from app.db.session import get_db
from app.main import app

DUMMY_HASH = "test-hash-not-used"


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_user_membership(db, *, organization_id: str, email: str, role: str) -> User:
    user = User(
        email=email,
        full_name=email.split("@", 1)[0],
        hashed_password=DUMMY_HASH,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        OrganizationMembership(
            organization_id=organization_id,
            user_id=user.id,
            role=role,
        )
    )
    db.flush()
    return user


def _create_alert(db, *, organization_id: str, dedupe_key: str, metric_key: str = "encounters_week") -> AnalyticsAlert:
    today = dt.datetime.now(dt.UTC).date()
    current_start = today - dt.timedelta(days=8)
    current_end = today - dt.timedelta(days=1)
    baseline_start = today - dt.timedelta(days=16)
    baseline_end = today - dt.timedelta(days=9)

    alert = AnalyticsAlert(
        id=str(uuid4()),
        organization_id=organization_id,
        alert_type="anomaly",
        metric_key=metric_key,
        report_key="executive_overview",
        baseline_window_days=7,
        comparison_period="current_vs_prior",
        current_range_start=current_start,
        current_range_end=current_end,
        baseline_range_start=baseline_start,
        baseline_range_end=baseline_end,
        current_value=10,
        baseline_value=5,
        delta_value=5,
        delta_pct=100,
        severity="high",
        title="Encounters up 100% vs prior 7d",
        summary="Synthetic alert for testing.",
        recommended_actions=["Review drivers"],
        context_filters={},
        status="open",
        acknowledged_at=None,
        resolved_at=None,
        dedupe_key=dedupe_key,
        created_at=dt.datetime.now(dt.UTC),
        updated_at=dt.datetime.now(dt.UTC),
    )
    db.add(alert)
    db.flush()
    return alert


def test_alert_routes_are_present_in_openapi() -> None:
    with TestClient(app) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    assert "/api/v1/analytics/alerts" in payload["paths"]
    assert "/api/v1/analytics/alerts/{alert_id}/acknowledge" in payload["paths"]
    assert "/api/v1/analytics/alerts/{alert_id}/resolve" in payload["paths"]


def test_alerts_list_is_tenant_scoped_and_requires_permission(tmp_path) -> None:
    database_file = tmp_path / "analytics_alerts.sqlite"
    engine = create_engine(
        f"sqlite:///{database_file}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    from app.db import models as _models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestingSessionLocal() as db:
            org1 = Organization(name="Alerts Org 1")
            org2 = Organization(name="Alerts Org 2")
            db.add_all([org1, org2])
            db.flush()

            admin1 = _create_user_membership(db, organization_id=org1.id, email="admin1@example.com", role=ROLE_ADMIN)
            receptionist1 = _create_user_membership(
                db,
                organization_id=org1.id,
                email="reception@example.com",
                role=ROLE_RECEPTIONIST,
            )
            _create_user_membership(db, organization_id=org2.id, email="admin2@example.com", role=ROLE_ADMIN)

            _create_alert(db, organization_id=org1.id, dedupe_key=f"{org1.id}:encounters_week:7:2026-01-01")
            _create_alert(db, organization_id=org2.id, dedupe_key=f"{org2.id}:encounters_week:7:2026-01-01")
            db.commit()

            admin_token = create_access_token({"sub": admin1.id, "org_id": org1.id})
            receptionist_token = create_access_token({"sub": receptionist1.id, "org_id": org1.id})

        with TestClient(app) as client:
            response = client.get(
                "/api/v1/analytics/alerts?status=open&limit=50",
                headers=_auth_header(admin_token),
            )
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["organization_id"] == org1.id

        with TestClient(app) as client:
            response = client.get(
                "/api/v1/analytics/alerts?status=open",
                headers=_auth_header(receptionist_token),
            )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_acknowledge_and_resolve_are_tenant_scoped_and_audited(tmp_path) -> None:
    database_file = tmp_path / "analytics_alerts_actions.sqlite"
    engine = create_engine(
        f"sqlite:///{database_file}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    from app.db import models as _models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestingSessionLocal() as db:
            org1 = Organization(name="Alerts Action Org 1")
            org2 = Organization(name="Alerts Action Org 2")
            db.add_all([org1, org2])
            db.flush()

            admin1 = _create_user_membership(db, organization_id=org1.id, email="admin-act1@example.com", role=ROLE_ADMIN)
            admin2 = _create_user_membership(db, organization_id=org2.id, email="admin-act2@example.com", role=ROLE_ADMIN)

            alert = _create_alert(db, organization_id=org1.id, dedupe_key=f"{org1.id}:encounters_week:7:2026-01-01")
            alert_id = alert.id
            db.commit()

            token1 = create_access_token({"sub": admin1.id, "org_id": org1.id})
            token2 = create_access_token({"sub": admin2.id, "org_id": org2.id})

        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/analytics/alerts/{alert_id}/acknowledge",
                headers=_auth_header(token1),
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "acknowledged"
        assert payload["acknowledged_at"] is not None

        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/analytics/alerts/{alert_id}/resolve",
                headers=_auth_header(token1),
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "resolved"
        assert payload["resolved_at"] is not None

        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/analytics/alerts/{alert_id}/acknowledge",
                headers=_auth_header(token2),
            )
        assert response.status_code == 404

        with TestingSessionLocal() as db:
            ack_event = db.execute(
                select(AuditEvent).where(
                    AuditEvent.organization_id == org1.id,
                    AuditEvent.action == "analytics.alert_acknowledged",
                )
            ).scalar_one_or_none()
            assert ack_event is not None

            resolve_event = db.execute(
                select(AuditEvent).where(
                    AuditEvent.organization_id == org1.id,
                    AuditEvent.action == "analytics.alert_resolved",
                )
            ).scalar_one_or_none()
            assert resolve_event is not None
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
