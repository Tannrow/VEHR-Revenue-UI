from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.v1.endpoints import revenue_era
from app.core.rbac import ROLE_ADMIN
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.revenue_era import RevenueEraClaimLine, RevenueEraFile, RevenueEraWorkItem
from app.db.models.user import User
from app.db.session import get_db
from app.main import app
from app.services.revenue_era import (
    MATCH_UNMATCHED,
    STATUS_ERROR,
    STATUS_NORMALIZED,
    RevenueEraStructuredLine,
    RevenueEraStructuredV1,
)


def _setup_sqlite(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path/'revenue_era.sqlite'}", connect_args={"check_same_thread": False})
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
    return TestingSessionLocal


def _seed_admin(db_session) -> tuple[str, str]:
    with db_session() as db:
        org = Organization(name="ERA Org")
        db.add(org)
        db.flush()

        user = User(
            email="admin@example.com",
            full_name="Admin",
            hashed_password=hash_password("Password123!"),
            is_active=True,
        )
        db.add(user)
        db.flush()

        db.add(OrganizationMembership(organization_id=org.id, user_id=user.id, role=ROLE_ADMIN))
        db.commit()
        token = create_access_token({"sub": user.id, "org_id": org.id})
        return token, org.id


def test_upload_rejects_duplicate_sha(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token, _ = _seed_admin(session_factory)

    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)

    try:
        with TestClient(app) as client:
            files = [("files", ("era.pdf", b"%PDF-1.4 era", "application/pdf"))]
            response = client.post(
                "/api/v1/revenue/era-pdfs/upload",
                files=files,
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200
            first = response.json()
            assert len(first) == 1

            response_dup = client.post(
                "/api/v1/revenue/era-pdfs/upload",
                files=files,
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response_dup.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_process_pipeline_creates_claims_and_worklist(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token, org_id = _seed_admin(session_factory)

    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)

    def _fake_docintel(path: Path):
        return {"model_id": "di-model", "extracted": {"ok": True, "path": str(path)}}

    structured = RevenueEraStructuredV1(
        payer_name="Payer One",
        received_date=date(2026, 1, 1),
        claim_lines=[
            RevenueEraStructuredLine(
                claim_ref="CLM123",
                service_date=date(2026, 1, 2),
                proc_code="99213",
                charge_cents=10000,
                allowed_cents=8000,
                paid_cents=5000,
                adjustments=[],
                match_status=MATCH_UNMATCHED,
            )
        ],
    )

    monkeypatch.setattr(revenue_era, "run_doc_intel", _fake_docintel)
    monkeypatch.setattr(revenue_era, "run_structuring_llm", lambda payload: structured)

    try:
        with TestClient(app) as client:
            files = [("files", ("era.pdf", b"%PDF-1.4 era", "application/pdf"))]
            upload = client.post(
                "/api/v1/revenue/era-pdfs/upload",
                files=files,
                headers={"Authorization": f"Bearer {token}"},
            )
            assert upload.status_code == 200
            era_id = upload.json()[0]["id"]

            process = client.post(
                f"/api/v1/revenue/era-pdfs/{era_id}/process",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert process.status_code == 200
            body = process.json()
            assert body["status"] == STATUS_NORMALIZED

        with session_factory() as db:
            file_row = db.get(RevenueEraFile, era_id)
            assert file_row.status == STATUS_NORMALIZED
            lines = (
                db.execute(select(RevenueEraClaimLine).where(RevenueEraClaimLine.era_file_id == era_id))
                .scalars()
                .all()
            )
            assert len(lines) == 1
            assert lines[0].claim_ref == "CLM123"
            worklist = (
                db.execute(select(RevenueEraWorkItem).where(RevenueEraWorkItem.organization_id == org_id))
                .scalars()
                .all()
            )
            assert len(worklist) == 1
            assert worklist[0].type == "UNDERPAYMENT"
    finally:
        app.dependency_overrides.clear()


def test_structuring_failure_sets_error_status(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token, _ = _seed_admin(session_factory)

    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(revenue_era, "run_doc_intel", lambda path: {"model_id": "x", "extracted": {"ok": True}})

    def _fail_structured(payload: dict[str, str]) -> RevenueEraStructuredV1:
        raise RuntimeError("bad schema")

    monkeypatch.setattr(revenue_era, "run_structuring_llm", _fail_structured)

    try:
        with TestClient(app) as client:
            files = [("files", ("era.pdf", b"%PDF-1.4 era", "application/pdf"))]
            upload = client.post(
                "/api/v1/revenue/era-pdfs/upload",
                files=files,
                headers={"Authorization": f"Bearer {token}"},
            )
            assert upload.status_code == 200
            era_id = upload.json()[0]["id"]

            process = client.post(
                f"/api/v1/revenue/era-pdfs/{era_id}/process",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert process.status_code == 502

        with session_factory() as db:
            file_row = db.get(RevenueEraFile, era_id)
            assert file_row.status == STATUS_ERROR
            lines = (
                db.execute(select(RevenueEraClaimLine).where(RevenueEraClaimLine.era_file_id == era_id))
                .scalars()
                .all()
            )
            assert not lines
            worklist = (
                db.execute(select(RevenueEraWorkItem).where(RevenueEraWorkItem.era_file_id == era_id))
                .scalars()
                .all()
            )
            assert not worklist
    finally:
        app.dependency_overrides.clear()
