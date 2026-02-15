from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.v1.endpoints import bi as bi_endpoint
from app.core.rbac import ROLE_ADMIN, ROLE_RECEPTIONIST
from app.core.security import create_access_token
from app.db.base import Base
from app.db.models.audit_event import AuditEvent
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.user import User
from app.db.session import get_db
from app.main import app
from app.services.bi import PowerBIEmbedToken, PowerBIReport

DUMMY_HASH = "test-hash-not-used"


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _setup_membership(db, *, role: str, email: str) -> tuple[str, str]:
    org = Organization(name="BI Test Org")
    db.add(org)
    db.flush()

    user = User(
        email=email,
        full_name=email.split("@", 1)[0],
        hashed_password=DUMMY_HASH,
        is_active=True,
    )
    db.add(user)
    db.flush()

    membership = OrganizationMembership(
        organization_id=org.id,
        user_id=user.id,
        role=role,
    )
    db.add(membership)
    db.commit()
    return user.id, org.id


def _set_bi_env(monkeypatch) -> None:
    monkeypatch.setenv("PBI_WORKSPACE_ID", "workspace-123")
    monkeypatch.setenv("PBI_REPORT_ID_CHART_AUDIT", "report-123")
    monkeypatch.setenv("PBI_DATASET_ID_CHART_AUDIT", "dataset-123")
    monkeypatch.setenv("PBI_RLS_ROLE", "TenantRLS")


def test_embed_config_uses_org_scoped_identity_and_logs_event(tmp_path, monkeypatch) -> None:
    database_file = tmp_path / "bi_embed_config.sqlite"
    engine = create_engine(
        f"sqlite:///{database_file}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    from app.db import models as _models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _set_bi_env(monkeypatch)

    class _FakePowerBIClient:
        def __init__(self) -> None:
            self.last_username: str | None = None
            self.last_role: str | None = None
            self.last_dataset_id: str | None = None

        def get_access_token(self) -> str:
            return "service-token"

        def get_report(self, *, workspace_id: str, report_id: str, access_token: str) -> PowerBIReport:
            assert workspace_id == "workspace-123"
            assert report_id == "report-123"
            assert access_token == "service-token"
            return PowerBIReport(
                id="report-123",
                name="Chart Audit",
                embed_url="https://app.powerbi.com/reportEmbed?reportId=report-123",
                dataset_id="dataset-123",
            )

        def generate_report_embed_token(
            self,
            *,
            workspace_id: str,
            report_id: str,
            dataset_id: str,
            username: str,
            rls_role: str,
            access_token: str,
        ) -> PowerBIEmbedToken:
            assert workspace_id == "workspace-123"
            assert report_id == "report-123"
            assert access_token == "service-token"
            self.last_username = username
            self.last_role = rls_role
            self.last_dataset_id = dataset_id
            return PowerBIEmbedToken(
                token="embed-token",
                expires_on="2026-12-31T23:59:59Z",
            )

    fake_client = _FakePowerBIClient()
    monkeypatch.setattr(
        bi_endpoint.PowerBIClient,
        "from_env",
        staticmethod(lambda: fake_client),
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestingSessionLocal() as db:
            user_id, org_id = _setup_membership(
                db,
                role=ROLE_ADMIN,
                email="admin-bi@example.com",
            )
            token = create_access_token({"sub": user_id, "org_id": org_id})

        with TestClient(app) as client:
            response = client.get(
                "/api/v1/bi/embed-config?report_key=chart_audit&org_id=should_not_be_used",
                headers=_auth_header(token),
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["type"] == "report"
        assert payload["reportId"] == "report-123"
        assert payload["embedUrl"].startswith("https://app.powerbi.com/reportEmbed")
        assert payload["accessToken"] == "embed-token"
        assert payload["expiresOn"] == "2026-12-31T23:59:59Z"

        assert fake_client.last_username == org_id
        assert fake_client.last_role == "TenantRLS"
        assert fake_client.last_dataset_id == "dataset-123"

        with TestingSessionLocal() as db:
            event = db.execute(
                select(AuditEvent).where(
                    AuditEvent.organization_id == org_id,
                    AuditEvent.action == "bi.embed_token_issued",
                )
            ).scalar_one_or_none()
            assert event is not None
            assert event.entity_id == "chart_audit"
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_embed_config_requires_analytics_permission(tmp_path, monkeypatch) -> None:
    database_file = tmp_path / "bi_embed_permission.sqlite"
    engine = create_engine(
        f"sqlite:///{database_file}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    from app.db import models as _models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _set_bi_env(monkeypatch)

    class _FakePowerBIClient:
        def get_access_token(self) -> str:
            return "service-token"

    monkeypatch.setattr(
        bi_endpoint.PowerBIClient,
        "from_env",
        staticmethod(lambda: _FakePowerBIClient()),
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestingSessionLocal() as db:
            user_id, org_id = _setup_membership(
                db,
                role=ROLE_RECEPTIONIST,
                email="reception-bi@example.com",
            )
            token = create_access_token({"sub": user_id, "org_id": org_id})

        with TestClient(app) as client:
            response = client.get(
                "/api/v1/bi/embed-config?report_key=chart_audit",
                headers=_auth_header(token),
            )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
