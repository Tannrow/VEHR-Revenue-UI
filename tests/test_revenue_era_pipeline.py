from __future__ import annotations

import json
import threading
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.api.v1.endpoints import revenue_era
from app.core.rbac import ROLE_ADMIN
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.revenue_era import (
    RevenueEraClaimLine,
    RevenueEraFile,
    RevenueEraProcessingLog,
    RevenueEraExtractResult,
    RevenueEraStructuredResult,
    RevenueEraValidationReport,
    RevenueEraWorkItem,
)
from app.db.models.user import User
from app.db.session import get_db
from app.main import app
from app.services.revenue_era import (
    MATCH_UNMATCHED,
    STATUS_ERROR,
    STATUS_UPLOADED,
    STATUS_NORMALIZED,
    STATUS_STRUCTURED,
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


def test_upload_openapi_schema_is_multipart_binary_array() -> None:
    schema = app.openapi()
    request_body = schema["paths"]["/api/v1/revenue/era-pdfs/upload"]["post"]["requestBody"]
    content = request_body["content"]["multipart/form-data"]["schema"]
    body_schema = schema["components"]["schemas"][content["$ref"].split("/")[-1]]
    properties = body_schema.get("properties", {})
    files_property = properties.get("files", {})

    assert request_body["required"] is True
    assert files_property["type"] == "array"
    assert files_property["items"] == {"type": "string", "format": "binary"}


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
        with session_factory() as db:
            rows = db.execute(select(RevenueEraFile)).scalars().all()
            assert len(rows) == 1
            assert rows[0].sha256
    finally:
        app.dependency_overrides.clear()


def test_upload_accepts_multiple_pdf_files(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token, _ = _seed_admin(session_factory)

    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)

    try:
        with TestClient(app) as client:
            files = [
                ("files", ("era-1.pdf", b"%PDF-1.4 era one", "application/pdf")),
                ("files", ("era-2.pdf", b"%PDF-1.4 era two", "application/pdf")),
            ]
            response = client.post(
                "/api/v1/revenue/era-pdfs/upload",
                files=files,
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200
            payload = response.json()
            assert len(payload) == 2
            for row in payload:
                assert {"id", "file_name", "status", "created_at"} <= row.keys()
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
            logs = (
                db.execute(select(RevenueEraProcessingLog).where(RevenueEraProcessingLog.era_file_id == era_id))
                .scalars()
                .all()
            )
            stages = {log.stage for log in logs}
            assert {"EXTRACTED", "STRUCTURED", "NORMALIZED"} <= stages
    finally:
        app.dependency_overrides.clear()


def test_claim_lines_unique_per_claim_key(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    _, org_id = _seed_admin(session_factory)

    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)

    try:
        with session_factory() as db:
            era_file = RevenueEraFile(
                organization_id=org_id,
                file_name="era.pdf",
                sha256="abc",
                storage_ref="s3://era.pdf",
                status="uploaded",
            )
            db.add(era_file)
            db.flush()

            line_one = RevenueEraClaimLine(
                era_file_id=era_file.id,
                line_index=0,
                claim_ref="CLM123",
                service_date=date(2026, 1, 2),
                proc_code="99213",
                match_status=MATCH_UNMATCHED,
            )
            line_two = RevenueEraClaimLine(
                era_file_id=era_file.id,
                line_index=1,
                claim_ref="CLM123",
                service_date=date(2026, 1, 2),
                proc_code="99213",
                match_status=MATCH_UNMATCHED,
            )
            db.add_all([line_one, line_two])
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
    finally:
        app.dependency_overrides.clear()


def test_structured_results_unique_per_file(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token, org_id = _seed_admin(session_factory)

    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)

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

        with session_factory() as db:
            first = RevenueEraStructuredResult(
                era_file_id=era_id,
                llm="gpt",
                deployment="deploy",
                api_version="v1",
                prompt_version="p1",
                structured_json={},
            )
            second = RevenueEraStructuredResult(
                era_file_id=era_id,
                llm="gpt",
                deployment="deploy",
                api_version="v1",
                prompt_version="p1",
                structured_json={},
            )
            db.add_all([first, second])
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
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
            assert process.json() == {"error": "external_service_failure", "stage": "structuring"}

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
            logs = (
                db.execute(select(RevenueEraProcessingLog).where(RevenueEraProcessingLog.era_file_id == era_id))
                .scalars()
                .all()
            )
            assert any(log.stage == "structuring" for log in logs)
    finally:
        app.dependency_overrides.clear()


def test_extract_failure_returns_external_service_error_payload(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token, _ = _seed_admin(session_factory)

    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)

    def _timeout_doc_intel(_path: Path):
        raise TimeoutError("timed out")

    monkeypatch.setattr(revenue_era, "run_doc_intel", _timeout_doc_intel)

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
            assert process.json() == {"error": "external_service_failure", "stage": "extract"}

        with session_factory() as db:
            file_row = db.get(RevenueEraFile, era_id)
            assert file_row.status == STATUS_ERROR
            logs = (
                db.execute(select(RevenueEraProcessingLog).where(RevenueEraProcessingLog.era_file_id == era_id))
                .scalars()
                .all()
            )
            assert any(log.stage == "extract" for log in logs)
    finally:
        app.dependency_overrides.clear()


def test_extract_failure_error_detail_is_sanitized(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token, _ = _seed_admin(session_factory)

    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)

    class _PhiLikeError(RuntimeError):
        pass

    def _phi_exception_doc_intel(_path: Path):
        raise _PhiLikeError("patient_name=John Doe member_id=12345")

    monkeypatch.setattr(revenue_era, "run_doc_intel", _phi_exception_doc_intel)

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
            assert process.json() == {"error": "external_service_failure", "stage": "extract"}

        with session_factory() as db:
            file_row = db.get(RevenueEraFile, era_id)
            assert file_row.status == STATUS_ERROR
            assert file_row.error_detail is not None
            assert "John Doe" not in file_row.error_detail
            assert "member_id=12345" not in file_row.error_detail
            detail = json.loads(file_row.error_detail)
            assert detail["error_code"] == "UNKNOWN_ERROR"
            assert detail["exception_type"] == "_PhiLikeError"
            assert detail["stage"] == "extract"
    finally:
        app.dependency_overrides.clear()


def test_process_phase2_failure_rolls_back_without_commits(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token, org_id = _seed_admin(session_factory)
    monkeypatch.setenv("PHASE2_VALIDATION", "1")
    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)

    def _fake_docintel(path: Path):
        return {"model_id": "di-model", "extracted": {"ok": True, "path": str(path)}}

    def _fail_structuring(_payload: dict[str, object]) -> RevenueEraStructuredV1:
        raise TimeoutError("timed out patient_name=Jane Doe")

    monkeypatch.setattr(revenue_era, "run_doc_intel", _fake_docintel)
    monkeypatch.setattr(revenue_era, "run_structuring_llm", _fail_structuring)

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
            assert process.json() == {"error": "external_service_failure", "stage": "structuring"}

        with session_factory() as db:
            file_row = db.get(RevenueEraFile, era_id)
            assert file_row.organization_id == org_id
            assert file_row.status == STATUS_ERROR
            assert "Jane Doe" not in (file_row.error_detail or "")
            assert len(
                db.execute(select(RevenueEraExtractResult).where(RevenueEraExtractResult.era_file_id == era_id))
                .scalars()
                .all()
            ) == 1
            assert (
                db.execute(select(RevenueEraStructuredResult).where(RevenueEraStructuredResult.era_file_id == era_id))
                .scalars()
                .all()
                == []
            )
            logs = (
                db.execute(select(RevenueEraProcessingLog).where(RevenueEraProcessingLog.era_file_id == era_id))
                .scalars()
                .all()
            )
            assert {"UPLOAD", "EXTRACTED"} <= {log.stage for log in logs}
            assert all("Jane Doe" not in (log.message or "") for log in logs)
    finally:
        app.dependency_overrides.clear()


def test_validation_failure_sets_error_status_and_logs(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token, _ = _seed_admin(session_factory)

    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(revenue_era, "run_doc_intel", lambda path: {"model_id": "x", "extracted": {"ok": True}})

    bad_payload = {"payer_name": "Payer", "claim_lines": [{"claim_ref": "CLM123", "patient_name": "Name"}]}
    try:
        RevenueEraStructuredV1.model_validate(bad_payload)
    except ValidationError as exc:
        validation_error = exc
    else:  # pragma: no cover - guardrail
        raise AssertionError("Expected validation error")

    def _raise_validation(_payload: dict[str, str]) -> RevenueEraStructuredV1:
        raise validation_error

    monkeypatch.setattr(revenue_era, "run_structuring_llm", _raise_validation)

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
            assert process.status_code == 422

        with session_factory() as db:
            file_row = db.get(RevenueEraFile, era_id)
            assert file_row.status == STATUS_ERROR
            assert (
                db.execute(select(RevenueEraClaimLine).where(RevenueEraClaimLine.era_file_id == era_id))
                .scalars()
                .all()
                == []
            )
            assert (
                db.execute(select(RevenueEraWorkItem).where(RevenueEraWorkItem.era_file_id == era_id))
                .scalars()
                .all()
                == []
            )
            logs = (
                db.execute(select(RevenueEraProcessingLog).where(RevenueEraProcessingLog.era_file_id == era_id))
                .scalars()
                .all()
            )
            assert any(log.stage == "ERROR" for log in logs)
    finally:
        app.dependency_overrides.clear()


def test_legacy_latest_endpoint_returns_deprecation(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token, _ = _seed_admin(session_factory)

    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/billing/recon/import/latest",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "deprecated"
            assert "ERA Intake" in body["message"]
    finally:
        app.dependency_overrides.clear()


def test_process_twice_does_not_duplicate_results(tmp_path, monkeypatch) -> None:
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

            first = client.post(
                f"/api/v1/revenue/era-pdfs/{era_id}/process",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert first.status_code == 200

            second = client.post(
                f"/api/v1/revenue/era-pdfs/{era_id}/process",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert second.status_code == 409
            assert second.json()["detail"]["error_code"] == "ERA_ALREADY_COMPLETE"

        with session_factory() as db:
            file_row = db.get(RevenueEraFile, era_id)
            assert file_row.status == STATUS_NORMALIZED
            lines = (
                db.execute(select(RevenueEraClaimLine).where(RevenueEraClaimLine.era_file_id == era_id))
                .scalars()
                .all()
            )
            work_items = (
                db.execute(select(RevenueEraWorkItem).where(RevenueEraWorkItem.organization_id == org_id))
                .scalars()
                .all()
            )
            assert len(lines) == 1
            assert len(work_items) == 1
    finally:
        app.dependency_overrides.clear()


def test_process_noop_when_already_normalized(tmp_path, monkeypatch) -> None:
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

            first = client.post(
                f"/api/v1/revenue/era-pdfs/{era_id}/process",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert first.status_code == 200

            called: dict[str, bool] = {"docintel": False, "structuring": False}

            def _fail_docintel(_path: Path):
                called["docintel"] = True
                raise AssertionError("doc intel should not run for normalized file")

            def _fail_structuring(_payload: dict[str, object]):
                called["structuring"] = True
                raise AssertionError("structuring should not run for normalized file")

            monkeypatch.setattr(revenue_era, "run_doc_intel", _fail_docintel)
            monkeypatch.setattr(revenue_era, "run_structuring_llm", _fail_structuring)

            second = client.post(
                f"/api/v1/revenue/era-pdfs/{era_id}/process",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert second.status_code == 409
            assert second.json()["detail"]["error_code"] == "ERA_ALREADY_COMPLETE"
            assert called == {"docintel": False, "structuring": False}

        with session_factory() as db:
            file_row = db.get(RevenueEraFile, era_id)
            assert file_row.status == STATUS_NORMALIZED
            lines = (
                db.execute(select(RevenueEraClaimLine).where(RevenueEraClaimLine.era_file_id == era_id))
                .scalars()
                .all()
            )
            work_items = (
                db.execute(select(RevenueEraWorkItem).where(RevenueEraWorkItem.organization_id == org_id))
                .scalars()
                .all()
            )
            assert len(lines) == 1
            assert len(work_items) == 1
    finally:
        app.dependency_overrides.clear()


def test_process_error_conflict_returns_state_and_diagnostics_endpoint(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token, _ = _seed_admin(session_factory)
    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)

    def _timeout_doc_intel(_path: Path):
        raise TimeoutError("timed out")

    monkeypatch.setattr(revenue_era, "run_doc_intel", _timeout_doc_intel)

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

            first = client.post(
                f"/api/v1/revenue/era-pdfs/{era_id}/process",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert first.status_code == 502
            assert first.json() == {"error": "external_service_failure", "stage": "extract"}

            second = client.post(
                f"/api/v1/revenue/era-pdfs/{era_id}/process",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert second.status_code == 409
            detail = second.json()["detail"]
            assert detail["error_code"] == "ERA_INVALID_STATE"
            assert detail["era_file_id"] == era_id
            assert detail["current_status"] == STATUS_ERROR
            assert detail["retry_required"] is True

            diagnostics = client.get(
                f"/api/v1/revenue/era-pdfs/{era_id}/diagnostics",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert diagnostics.status_code == 200
            body = diagnostics.json()
            assert body["era_file_id"] == era_id
            assert body["current_status"] == STATUS_ERROR
            assert body["retry_required"] is True
            assert body["has_extract_result"] is False
            assert body["has_structured_result"] is False
            assert body["last_error_code"] == "EXTRACT_TIMEOUT"
            assert body["last_error_stage"] == "extract"
            assert "error_detail" not in body
            assert "exception_type" not in body
    finally:
        app.dependency_overrides.clear()


def test_process_processing_structuring_state_returns_in_progress(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token, _ = _seed_admin(session_factory)

    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)

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

        structured = RevenueEraStructuredV1(
            payer_name="Payer One",
            received_date=date(2026, 1, 1),
            claim_lines=[
                RevenueEraStructuredLine(
                    claim_ref="CLM123",
                    service_date=date(2026, 1, 2),
                    proc_code="99213",
                    charge_cents=10000,
                    allowed_cents=9000,
                    paid_cents=7000,
                    adjustments=[],
                    match_status=MATCH_UNMATCHED,
                )
            ],
        )

        with session_factory() as db:
            era_file = db.get(RevenueEraFile, era_id)
            era_file.status = STATUS_STRUCTURED
            db.add(
                RevenueEraExtractResult(
                    era_file_id=era_id,
                    extractor="azure_doc_intelligence",
                    model_id="di-model",
                    extracted_json={"ok": True},
                )
            )
            db.add(
                RevenueEraStructuredResult(
                    era_file_id=era_id,
                    llm="gpt",
                    deployment="deploy",
                    api_version="v1",
                    prompt_version="p1",
                    structured_json=structured.model_dump(mode="json"),
                )
            )
            db.commit()

        called: dict[str, bool] = {"docintel": False, "structuring": False}

        def _fail_docintel(_path: Path):
            called["docintel"] = True
            raise AssertionError("doc intel should not run when structured result exists")

        def _fail_structuring(_payload: dict[str, object]):
            called["structuring"] = True
            raise AssertionError("structuring should not run when structured result exists")

        monkeypatch.setattr(revenue_era, "run_doc_intel", _fail_docintel)
        monkeypatch.setattr(revenue_era, "run_structuring_llm", _fail_structuring)

        with TestClient(app) as client:
            process = client.post(
                f"/api/v1/revenue/era-pdfs/{era_id}/process",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert process.status_code == 409
            assert process.json()["detail"]["error_code"] == "ERA_IN_PROGRESS"

        assert called == {"docintel": False, "structuring": False}

        with session_factory() as db:
            file_row = db.get(RevenueEraFile, era_id)
            assert file_row.status == STATUS_STRUCTURED
    finally:
        app.dependency_overrides.clear()


def test_double_process_call_returns_in_progress_conflict(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token, _ = _seed_admin(session_factory)
    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)

    started = threading.Event()
    release = threading.Event()

    def _blocking_docintel(_path: Path):
        started.set()
        assert release.wait(timeout=5)
        return {"model_id": "di-model", "extracted": {"ok": True}}

    structured = RevenueEraStructuredV1(
        payer_name="Payer One",
        claim_lines=[RevenueEraStructuredLine(claim_ref="CLM123", match_status=MATCH_UNMATCHED)],
    )

    monkeypatch.setattr(revenue_era, "run_doc_intel", _blocking_docintel)
    monkeypatch.setattr(revenue_era, "run_structuring_llm", lambda payload: structured)

    try:
        with TestClient(app) as client:
            upload = client.post(
                "/api/v1/revenue/era-pdfs/upload",
                files=[("files", ("era.pdf", b"%PDF-1.4 era", "application/pdf"))],
                headers={"Authorization": f"Bearer {token}"},
            )
            assert upload.status_code == 200
            era_id = upload.json()[0]["id"]

            first_result: dict[str, int] = {}

            def _first_call() -> None:
                response = client.post(
                    f"/api/v1/revenue/era-pdfs/{era_id}/process",
                    headers={"Authorization": f"Bearer {token}"},
                )
                first_result["status_code"] = response.status_code

            thread = threading.Thread(target=_first_call)
            thread.start()
            assert started.wait(timeout=5)

            second = client.post(
                f"/api/v1/revenue/era-pdfs/{era_id}/process",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert second.status_code == 409
            assert second.json()["detail"]["error_code"] == "ERA_IN_PROGRESS"

            release.set()
            thread.join(timeout=5)
            assert first_result["status_code"] == 200

        with session_factory() as db:
            file_row = db.get(RevenueEraFile, era_id)
            assert file_row.status == STATUS_NORMALIZED
            assert file_row.current_stage == "complete"
            extract_rows = (
                db.execute(select(RevenueEraExtractResult).where(RevenueEraExtractResult.era_file_id == era_id))
                .scalars()
                .all()
            )
            assert len(extract_rows) == 1
    finally:
        app.dependency_overrides.clear()


def test_retry_resets_pipeline_and_reprocesses(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token, org_id = _seed_admin(session_factory)
    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)

    fail_extract = {"value": True}

    def _docintel(_path: Path):
        if fail_extract["value"]:
            raise TimeoutError("timed out")
        return {"model_id": "di-model", "extracted": {"ok": True}}

    structured = RevenueEraStructuredV1(
        payer_name="Payer One",
        claim_lines=[RevenueEraStructuredLine(claim_ref="CLM123", match_status=MATCH_UNMATCHED)],
    )

    monkeypatch.setattr(revenue_era, "run_doc_intel", _docintel)
    monkeypatch.setattr(revenue_era, "run_structuring_llm", lambda payload: structured)

    try:
        with TestClient(app) as client:
            upload = client.post(
                "/api/v1/revenue/era-pdfs/upload",
                files=[("files", ("era.pdf", b"%PDF-1.4 era", "application/pdf"))],
                headers={"Authorization": f"Bearer {token}"},
            )
            assert upload.status_code == 200
            era_id = upload.json()[0]["id"]

            first = client.post(
                f"/api/v1/revenue/era-pdfs/{era_id}/process",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert first.status_code == 502

            blocked = client.post(
                f"/api/v1/revenue/era-pdfs/{era_id}/process",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert blocked.status_code == 409
            assert blocked.json()["detail"]["error_code"] == "ERA_INVALID_STATE"

        with session_factory() as db:
            db.add(
                RevenueEraExtractResult(
                    era_file_id=era_id,
                    extractor="azure_doc_intelligence",
                    model_id="old-di",
                    extracted_json={"stale": True},
                )
            )
            db.add(
                RevenueEraStructuredResult(
                    era_file_id=era_id,
                    llm="gpt",
                    deployment="old",
                    api_version="v1",
                    prompt_version="p1",
                    structured_json=structured.model_dump(mode="json"),
                )
            )
            db.add(
                RevenueEraClaimLine(
                    era_file_id=era_id,
                    line_index=0,
                    claim_ref="OLD",
                    service_date=None,
                    proc_code=None,
                    charge_cents=1,
                    allowed_cents=1,
                    paid_cents=1,
                    adjustments_json=[],
                    match_status=MATCH_UNMATCHED,
                )
            )
            db.add(
                RevenueEraWorkItem(
                    organization_id=org_id,
                    era_file_id=era_id,
                    era_claim_line_id=None,
                    type="REVIEW_REQUIRED",
                    dollars_cents=1,
                    payer_name="Old",
                    claim_ref="OLD",
                    status="OPEN",
                )
            )
            db.commit()

        fail_extract["value"] = False
        with TestClient(app) as client:
            retried = client.post(
                f"/api/v1/revenue/era-pdfs/{era_id}/process?retry=true",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert retried.status_code == 200

        with session_factory() as db:
            file_row = db.get(RevenueEraFile, era_id)
            assert file_row.status == STATUS_NORMALIZED
            assert file_row.last_error_stage is None
            extract_rows = (
                db.execute(select(RevenueEraExtractResult).where(RevenueEraExtractResult.era_file_id == era_id))
                .scalars()
                .all()
            )
            structured_rows = (
                db.execute(select(RevenueEraStructuredResult).where(RevenueEraStructuredResult.era_file_id == era_id))
                .scalars()
                .all()
            )
            claim_rows = (
                db.execute(select(RevenueEraClaimLine).where(RevenueEraClaimLine.era_file_id == era_id))
                .scalars()
                .all()
            )
            work_rows = (
                db.execute(select(RevenueEraWorkItem).where(RevenueEraWorkItem.era_file_id == era_id))
                .scalars()
                .all()
            )
            assert len(extract_rows) == 1
            assert extract_rows[0].model_id == "di-model"
            assert len(structured_rows) == 1
            assert len(claim_rows) == 1
            assert claim_rows[0].claim_ref == "CLM123"
            assert len(work_rows) == 1
            logs = (
                db.execute(select(RevenueEraProcessingLog).where(RevenueEraProcessingLog.era_file_id == era_id))
                .scalars()
                .all()
            )
            assert any(log.message == "event=retry_reset" for log in logs)
    finally:
        app.dependency_overrides.clear()


def test_normalization_failure_rolls_back_claims(tmp_path, monkeypatch) -> None:
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

    def _bad_normalize(db, *, era_file, structured):
        db.add(
            RevenueEraClaimLine(
                era_file_id=era_file.id,
                line_index=0,
                claim_ref="CLM123",
                service_date=date(2026, 1, 2),
                proc_code="99213",
                match_status=MATCH_UNMATCHED,
            )
        )
        db.flush()
        raise RuntimeError("boom")

    monkeypatch.setattr(revenue_era, "run_doc_intel", _fake_docintel)
    monkeypatch.setattr(revenue_era, "run_structuring_llm", lambda payload: structured)
    monkeypatch.setattr(revenue_era, "normalize_structured", _bad_normalize)

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
            assert process.status_code == 500

        with session_factory() as db:
            file_row = db.get(RevenueEraFile, era_id)
            assert file_row.status == STATUS_ERROR
            assert (
                db.execute(select(RevenueEraClaimLine).where(RevenueEraClaimLine.era_file_id == era_id))
                .scalars()
                .all()
                == []
            )
            assert (
                db.execute(select(RevenueEraWorkItem).where(RevenueEraWorkItem.organization_id == org_id))
                .scalars()
                .all()
                == []
            )
    finally:
        app.dependency_overrides.clear()


def test_process_respects_org_scope(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token_org1, org_id1 = _seed_admin(session_factory)

    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(revenue_era, "run_doc_intel", lambda path: {"model_id": "di-model", "extracted": {"ok": True}})
    monkeypatch.setattr(
        revenue_era,
        "run_structuring_llm",
        lambda payload: RevenueEraStructuredV1(
            payer_name="Payer One",
            claim_lines=[RevenueEraStructuredLine(claim_ref="CLM123", match_status=MATCH_UNMATCHED)],
        ),
    )

    with session_factory() as db:
        org_two = Organization(name="ERA Org Two")
        db.add(org_two)
        db.flush()
        user_two = User(
            email="other@example.com",
            full_name="Other",
            hashed_password=hash_password("Password123!"),
            is_active=True,
        )
        db.add(user_two)
        db.flush()
        db.add(OrganizationMembership(organization_id=org_two.id, user_id=user_two.id, role=ROLE_ADMIN))
        db.commit()
        token_org2 = create_access_token({"sub": user_two.id, "org_id": org_two.id})

    try:
        with TestClient(app) as client:
            files = [("files", ("era.pdf", b"%PDF-1.4 era", "application/pdf"))]
            upload = client.post(
                "/api/v1/revenue/era-pdfs/upload",
                files=files,
                headers={"Authorization": f"Bearer {token_org1}"},
            )
            assert upload.status_code == 200
            era_id = upload.json()[0]["id"]

            process = client.post(
                f"/api/v1/revenue/era-pdfs/{era_id}/process",
                headers={"Authorization": f"Bearer {token_org2}"},
            )
            assert process.status_code == 404

        with session_factory() as db:
            file_row = db.get(RevenueEraFile, era_id)
            assert file_row.organization_id == org_id1
            assert file_row.status == STATUS_UPLOADED
    finally:
        app.dependency_overrides.clear()


def test_phase2_validate_duplicate_upload_returns_409_and_no_new_rows(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token, org_id = _seed_admin(session_factory)
    monkeypatch.setenv("PHASE2_VALIDATION", "1")
    monkeypatch.delenv("FAIL_CLOSED", raising=False)
    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(revenue_era, "run_doc_intel", lambda path: {"model_id": "x", "extracted": {"ok": True}})
    monkeypatch.setattr(
        revenue_era,
        "run_structuring_llm",
        lambda payload: RevenueEraStructuredV1(
            payer_name="Payer",
            claim_lines=[RevenueEraStructuredLine(claim_ref="CLM1", charge_cents=100, paid_cents=90)],
        ),
    )
    try:
        with TestClient(app) as client:
            files = {"file": ("era.pdf", b"%PDF-1.4 data", "application/pdf")}
            first = client.post("/api/v1/era/validate", files=files, headers={"Authorization": f"Bearer {token}"})
            assert first.status_code == 200

            second = client.post("/api/v1/era/validate", files=files, headers={"Authorization": f"Bearer {token}"})
            assert second.status_code == 409
            payload = second.json()["detail"]
            assert payload["error_code"] == "ERA_DUPLICATE"
            assert payload["era_file_id"] == first.json()["era_file_id"]

        with session_factory() as db:
            assert len(db.execute(select(RevenueEraFile).where(RevenueEraFile.organization_id == org_id)).scalars().all()) == 1
            assert (
                len(
                    db.execute(
                        select(RevenueEraValidationReport).where(RevenueEraValidationReport.org_id == org_id)
                    )
                    .scalars()
                    .all()
                )
                == 1
            )
    finally:
        app.dependency_overrides.clear()


def test_phase2_validate_phi_detection_blocks_ingestion(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token, org_id = _seed_admin(session_factory)
    monkeypatch.setenv("PHASE2_VALIDATION", "1")
    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(revenue_era, "run_doc_intel", lambda path: {"model_id": "x", "extracted": {"ok": True}})
    monkeypatch.setattr(
        revenue_era,
        "run_structuring_llm",
        lambda payload: RevenueEraStructuredV1(
            payer_name="billing@example.com",
            claim_lines=[RevenueEraStructuredLine(claim_ref="CLM1", charge_cents=100, paid_cents=90)],
        ),
    )
    try:
        with TestClient(app) as client:
            files = {"file": ("era.pdf", b"%PDF-1.4 data", "application/pdf")}
            response = client.post("/api/v1/era/validate", files=files, headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 422
            assert response.json()["detail"]["error_code"] == "ERA_PHI_DETECTED"

        with session_factory() as db:
            assert db.execute(select(RevenueEraFile).where(RevenueEraFile.organization_id == org_id)).scalars().all() == []
            assert (
                db.execute(select(RevenueEraValidationReport).where(RevenueEraValidationReport.org_id == org_id))
                .scalars()
                .all()
                == []
            )
    finally:
        app.dependency_overrides.clear()


def test_phase2_validate_schema_failure_rolls_back_all_rows(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token, org_id = _seed_admin(session_factory)
    monkeypatch.setenv("PHASE2_VALIDATION", "1")
    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(revenue_era, "run_doc_intel", lambda path: {"model_id": "x", "extracted": {"ok": True}})

    bad_payload = {"payer_name": "Payer", "claim_lines": [{"claim_ref": "CLM123", "patient_name": "Name"}]}
    try:
        RevenueEraStructuredV1.model_validate(bad_payload)
    except ValidationError as exc:
        validation_error = exc
    else:  # pragma: no cover
        raise AssertionError("Expected validation error")
    monkeypatch.setattr(revenue_era, "run_structuring_llm", lambda payload: (_ for _ in ()).throw(validation_error))
    try:
        with TestClient(app) as client:
            files = {"file": ("era.pdf", b"%PDF-1.4 data", "application/pdf")}
            response = client.post("/api/v1/era/validate", files=files, headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 422
            assert response.json()["detail"]["error_code"] == "ERA_SCHEMA_INVALID"

        with session_factory() as db:
            assert db.execute(select(RevenueEraFile).where(RevenueEraFile.organization_id == org_id)).scalars().all() == []
            assert db.execute(select(RevenueEraExtractResult)).scalars().all() == []
            assert db.execute(select(RevenueEraStructuredResult)).scalars().all() == []
            assert db.execute(select(RevenueEraClaimLine)).scalars().all() == []
            assert db.execute(select(RevenueEraWorkItem)).scalars().all() == []
            assert db.execute(select(RevenueEraValidationReport)).scalars().all() == []
    finally:
        app.dependency_overrides.clear()


def test_float_and_decimal_amounts_rejected() -> None:
    with pytest.raises(ValidationError):
        RevenueEraStructuredLine.model_validate({"claim_ref": "X", "charge_cents": 1.5})
    with pytest.raises(ValidationError):
        RevenueEraStructuredLine.model_validate({"claim_ref": "X", "charge_cents": Decimal("10.0")})


def test_worklist_sorting_is_deterministic_with_tiebreaker(tmp_path, monkeypatch) -> None:
    session_factory = _setup_sqlite(tmp_path)
    token, org_id = _seed_admin(session_factory)
    monkeypatch.setattr(revenue_era, "_repo_root", lambda: tmp_path)
    try:
        with session_factory() as db:
            era_file = RevenueEraFile(
                organization_id=org_id,
                file_name="era.pdf",
                sha256="sha",
                storage_ref="s3://era.pdf",
                status=STATUS_NORMALIZED,
            )
            db.add(era_file)
            db.flush()
            first = RevenueEraWorkItem(
                organization_id=org_id,
                era_file_id=era_file.id,
                era_claim_line_id=None,
                type="REVIEW_REQUIRED",
                dollars_cents=5000,
                payer_name="Payer",
                claim_ref="A",
                status="OPEN",
            )
            second = RevenueEraWorkItem(
                organization_id=org_id,
                era_file_id=era_file.id,
                era_claim_line_id=None,
                type="REVIEW_REQUIRED",
                dollars_cents=5000,
                payer_name="Payer",
                claim_ref="B",
                status="OPEN",
            )
            db.add_all([first, second])
            db.flush()
            first.created_at = datetime(2026, 1, 1)
            second.created_at = datetime(2026, 1, 2)
            db.commit()

        with TestClient(app) as client:
            response = client.get("/api/v1/revenue/era-worklist", headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 200
            payload = response.json()
            assert payload[0]["claim_ref"] == "A"
            assert payload[1]["claim_ref"] == "B"
    finally:
        app.dependency_overrides.clear()
