from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.v1.endpoints import bi as bi_endpoint
from app.core.rbac import ROLE_ADMIN, ROLE_RECEPTIONIST
from app.core.security import create_access_token
from app.db.base import Base
from app.db.models.audit_event import AuditEvent
from app.db.models.bi_report import BIReport
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.user import User
from app.db.session import get_db
from app.main import app
from app.services.bi import PowerBIEmbedToken, PowerBIReport

DUMMY_HASH = "test-hash-not-used"
DEFAULT_WORKSPACE_ID = "b64502e3-dc61-413b-9666-96e106133208"
DEFAULT_REPORT_ID = "654a0794-ab05-43f4-ac9b-9a968203a361"
DEFAULT_DATASET_ID = "3737a027-ff43-477c-970a-54aed93cc8ed"


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


def _create_bi_report(
    db,
    *,
    report_key: str,
    name: str | None,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    report_id: str = DEFAULT_REPORT_ID,
    dataset_id: str = DEFAULT_DATASET_ID,
    rls_role: str = "TenantRLS",
    is_enabled: bool = True,
) -> BIReport:
    row = BIReport(
        report_key=report_key,
        name=name,
        workspace_id=workspace_id,
        report_id=report_id,
        dataset_id=dataset_id,
        rls_role=rls_role,
        is_enabled=is_enabled,
    )
    db.add(row)
    db.flush()
    return row


def test_bi_routes_are_present_in_openapi() -> None:
    with TestClient(app) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    assert "/api/v1/bi/embed-config" in payload["paths"]
    assert "/api/v1/bi/reports" in payload["paths"]


def test_embed_config_uses_db_registry_identity_and_logs_event(tmp_path, monkeypatch) -> None:
    database_file = tmp_path / "bi_embed_registry.sqlite"
    engine = create_engine(
        f"sqlite:///{database_file}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    from app.db import models as _models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    class _FakePowerBIClient:
        def __init__(self) -> None:
            self.last_username: str | None = None
            self.last_role: str | None = None
            self.last_dataset_id: str | None = None
            self.last_workspace_id: str | None = None
            self.last_report_id: str | None = None

        def get_access_token(self) -> str:
            return "service-token"

        def get_report(self, *, workspace_id: str, report_id: str, access_token: str) -> PowerBIReport:
            assert access_token == "service-token"
            self.last_workspace_id = workspace_id
            self.last_report_id = report_id
            return PowerBIReport(
                id=report_id,
                name="Chart Audit",
                embed_url=f"https://app.powerbi.com/reportEmbed?reportId={report_id}",
                dataset_id=DEFAULT_DATASET_ID,
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
            assert access_token == "service-token"
            self.last_workspace_id = workspace_id
            self.last_report_id = report_id
            self.last_dataset_id = dataset_id
            self.last_username = username
            self.last_role = rls_role
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
            org = Organization(name="BI Registry Org")
            db.add(org)
            db.flush()
            org_id = org.id

            admin = _create_user_membership(
                db,
                organization_id=org_id,
                email="admin-bi@example.com",
                role=ROLE_ADMIN,
            )
            _create_bi_report(
                db,
                report_key="chart_audit",
                name="Chart Audit",
            )
            db.commit()
            admin_token = create_access_token({"sub": admin.id, "org_id": org_id})

        with TestClient(app) as client:
            response = client.get(
                "/api/v1/bi/embed-config?report_key=chart_audit&org_id=ignored",
                headers=_auth_header(admin_token),
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["reportId"] == DEFAULT_REPORT_ID
        assert payload["embedUrl"].startswith("https://app.powerbi.com/reportEmbed")
        assert payload["accessToken"] == "embed-token"
        assert payload["expiresOn"] == "2026-12-31T23:59:59Z"

        assert fake_client.last_workspace_id == DEFAULT_WORKSPACE_ID
        assert fake_client.last_report_id == DEFAULT_REPORT_ID
        assert fake_client.last_dataset_id == DEFAULT_DATASET_ID
        assert fake_client.last_username == org_id
        assert fake_client.last_role == "TenantRLS"

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


def test_reports_endpoint_returns_enabled_reports_only(tmp_path) -> None:
    database_file = tmp_path / "bi_reports_list.sqlite"
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
            org = Organization(name="BI Reports Org")
            db.add(org)
            db.flush()

            admin = _create_user_membership(
                db,
                organization_id=org.id,
                email="reports-admin@example.com",
                role=ROLE_ADMIN,
            )
            _create_bi_report(db, report_key="chart_audit", name="Chart Audit", is_enabled=True)
            _create_bi_report(db, report_key="old_report", name="Old Report", is_enabled=False)
            db.commit()
            token = create_access_token({"sub": admin.id, "org_id": org.id})

        with TestClient(app) as client:
            response = client.get(
                "/api/v1/bi/reports",
                headers=_auth_header(token),
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload == [{"key": "chart_audit", "name": "Chart Audit"}]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_embed_config_requires_analytics_permission(tmp_path) -> None:
    database_file = tmp_path / "bi_permission.sqlite"
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
            org = Organization(name="BI Permission Org")
            db.add(org)
            db.flush()

            receptionist = _create_user_membership(
                db,
                organization_id=org.id,
                email="reception-bi@example.com",
                role=ROLE_RECEPTIONIST,
            )
            _create_bi_report(db, report_key="chart_audit", name="Chart Audit", is_enabled=True)
            db.commit()
            token = create_access_token({"sub": receptionist.id, "org_id": org.id})

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
