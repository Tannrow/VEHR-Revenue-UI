import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import date, datetime
from pathlib import Path
from typing import Any, List
from uuid import uuid4

import httpx
import requests
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

try:
    from azure.core.exceptions import AzureError
except Exception:  # pragma: no cover - fallback when azure libs are unavailable in local test env
    class AzureError(Exception):
        pass

from app.core.deps import get_current_membership, get_current_organization, require_permission
from app.core.time import utc_now
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.revenue_era import (
    RevenueEraClaimLine,
    RevenueEraExtractResult,
    RevenueEraFile,
    RevenueEraStructuredResult,
    RevenueEraValidationReport,
    RevenueEraWorkItem,
)
from app.db.session import get_db
from app.services.revenue_era import (
    STATUS_COMPLETE,
    STATUS_ERROR,
    STATUS_EXTRACTED,
    STATUS_NORMALIZED,
    STATUS_PROCESSING_EXTRACT,
    STATUS_PROCESSING_STRUCTURING,
    STATUS_STRUCTURED,
    STATUS_UPLOADED,
    WORKITEM_OPEN,
    ERROR_CODE_DUPLICATE,
    ERROR_CODE_PHI_DETECTED,
    ERROR_CODE_PROCESSING_FAILED,
    ERROR_CODE_RECONCILIATION_FAILED,
    ERROR_CODE_SCHEMA_INVALID,
    EraPhiDetectedError,
    EraReconciliationError,
    EraSchemaInvalidError,
    fail_closed_enabled,
    log_attempt,
    normalize_structured,
    phi_scan,
    phase2_validation_enabled,
    reconcile_era,
    record_processing_log,
    RevenueEraStructuredV1,
    run_doc_intel,
    run_structuring_llm,
    store_revenue_file,
    write_pdf_with_sha,
    summarize_validation_error,
)
from app.services.storage import sanitize_filename

router = APIRouter(tags=["Revenue ERA"])
logger = logging.getLogger(__name__)


class EraFileResponse(BaseModel):
    id: str
    file_name: str
    status: str
    payer_name_raw: str | None = None
    received_date: date | None = None
    error_detail: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkItemResponse(BaseModel):
    id: str
    type: str
    payer_name: str
    claim_ref: str
    dollars_cents: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ValidationTotalsResponse(BaseModel):
    paid: int
    adjustment: int
    patient_responsibility: int
    net: int


class EraValidateResponse(BaseModel):
    era_file_id: str
    reconciled: bool
    declared_total_missing: bool
    claim_count: int
    line_count: int
    work_item_count: int
    totals_cents: ValidationTotalsResponse
    top_work_items: list[WorkItemResponse]


class EraReportResponse(BaseModel):
    era_file_id: str
    claim_count: int
    line_count: int
    work_item_count: int
    total_paid_cents: int
    total_adjustment_cents: int
    total_patient_resp_cents: int
    net_cents: int
    reconciled: bool
    declared_total_missing: bool
    phi_scan_passed: bool
    phi_hit_count: int
    finalized: bool
    created_at: datetime
    top_work_items: list[WorkItemResponse]


class EraProcessDiagnosticsResponse(BaseModel):
    era_file_id: str
    current_status: str
    current_stage: str | None = None
    stage_started_at: datetime | None = None
    stage_completed_at: datetime | None = None
    retry_required: bool
    has_extract_result: bool
    has_structured_result: bool
    finalized: bool | None = None
    last_error_code: str | None = None
    last_error_stage: str | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _era_file_or_404(db: Session, *, era_file_id: str, organization_id: str) -> RevenueEraFile:
    row = db.get(RevenueEraFile, era_file_id)
    if not row or row.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="era_file_not_found")
    return row


def _latest_extract_result(db: Session, era_file_id: str) -> RevenueEraExtractResult | None:
    return (
        db.execute(
            select(RevenueEraExtractResult)
            .where(RevenueEraExtractResult.era_file_id == era_file_id)
            .order_by(RevenueEraExtractResult.extracted_at.desc(), RevenueEraExtractResult.id.desc())
        )
        .scalars()
        .first()
    )


def _latest_structured_result(db: Session, era_file_id: str) -> RevenueEraStructuredResult | None:
    return (
        db.execute(
            select(RevenueEraStructuredResult)
            .where(RevenueEraStructuredResult.era_file_id == era_file_id)
            .order_by(RevenueEraStructuredResult.created_at.desc(), RevenueEraStructuredResult.id.desc())
        )
        .scalars()
        .first()
    )


def _raise_phase2_error(http_status: int, *, error_code: str, era_file_id: str | None = None) -> None:
    detail: dict[str, Any] = {"error_code": error_code}
    if era_file_id:
        detail["era_file_id"] = era_file_id
    raise HTTPException(status_code=http_status, detail=detail)


def _top_work_items(db: Session, *, organization_id: str, era_file_id: str, limit: int = 50) -> list[RevenueEraWorkItem]:
    return (
        db.execute(
            select(RevenueEraWorkItem)
            .where(
                RevenueEraWorkItem.organization_id == organization_id,
                RevenueEraWorkItem.era_file_id == era_file_id,
            )
            .order_by(RevenueEraWorkItem.dollars_cents.desc(), RevenueEraWorkItem.created_at.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


def _latest_validation_report(
    db: Session,
    *,
    organization_id: str,
    era_file_id: str,
) -> RevenueEraValidationReport | None:
    return (
        db.execute(
            select(RevenueEraValidationReport)
            .where(
                RevenueEraValidationReport.org_id == organization_id,
                RevenueEraValidationReport.era_file_id == era_file_id,
            )
            .order_by(RevenueEraValidationReport.created_at.desc(), RevenueEraValidationReport.id.desc())
        )
        .scalars()
        .first()
    )


def _safe_error_metadata(error_detail: str | None) -> tuple[str | None, str | None]:
    if not error_detail:
        return None, None
    try:
        parsed = json.loads(error_detail)
    except Exception:
        return None, None
    if not isinstance(parsed, dict):
        return None, None
    error_code = parsed.get("error_code")
    stage = parsed.get("stage")
    safe_error_code = str(error_code) if isinstance(error_code, str) else None
    safe_stage = str(stage) if isinstance(stage, str) else None
    return safe_error_code, safe_stage


@router.post("/revenue/era-pdfs/upload", response_model=list[EraFileResponse])
async def upload_era_pdfs(
    files: List[UploadFile] = File(..., description="PDF files", media_type="application/pdf"),
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("billing:write")),
) -> list[EraFileResponse]:
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no_files_provided")

    repo_root = _repo_root()
    upload_dir = repo_root / "uploads" / "revenue_era" / organization.id
    upload_dir.mkdir(parents=True, exist_ok=True)

    created: list[RevenueEraFile] = []
    for upload in files:
        file_id = str(uuid4())
        safe_name = sanitize_filename(upload.filename or "upload.pdf")
        temp_path = upload_dir / f"{file_id}__{safe_name}.uploading"
        final_rel = Path("uploads") / "revenue_era" / organization.id / f"{file_id}__{safe_name}"
        try:
            sha256, _ = await write_pdf_with_sha(upload, temp_path)
            duplicate = db.execute(
                select(RevenueEraFile).where(
                    RevenueEraFile.organization_id == organization.id,
                    RevenueEraFile.sha256 == sha256,
                )
            ).scalar_one_or_none()
            if duplicate:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="duplicate_upload")

            final_path = repo_root / final_rel
            os.replace(temp_path, final_path)
            row = store_revenue_file(
                db,
                organization_id=organization.id,
                file_name=safe_name,
                sha256=sha256,
                storage_ref=final_rel.as_posix(),
                payer_name_raw=None,
                received_date=None,
            )
            created.append(row)
            record_processing_log(
                db,
                era_file_id=row.id,
                stage="UPLOAD",
                message=f"file_name={safe_name}",
            )
            log_attempt(
                db,
                organization_id=organization.id,
                actor=membership.user.email,
                era_file_id=row.id,
                action="era_pdf_uploaded",
            )
        except HTTPException:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise
        except Exception as exc:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="upload_failed",
            ) from exc

    return created


@router.post("/era/validate", response_model=EraValidateResponse)
async def validate_era_pdf(
    file: UploadFile = File(..., description="ERA PDF file", media_type="application/pdf"),
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("billing:write")),
) -> EraValidateResponse:
    strict_mode = phase2_validation_enabled()
    fail_closed = fail_closed_enabled() if strict_mode else False
    repo_root = _repo_root()
    upload_dir = repo_root / "uploads" / "revenue_era" / organization.id
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = str(uuid4())
    safe_name = sanitize_filename(file.filename or "upload.pdf")
    temp_path = upload_dir / f"{file_id}__{safe_name}.uploading"
    final_rel = Path("uploads") / "revenue_era" / organization.id / f"{file_id}__{safe_name}"
    final_path = repo_root / final_rel
    era_file_id: str | None = None

    try:
        sha256, _ = await write_pdf_with_sha(file, temp_path)

        duplicate = db.execute(
            select(RevenueEraFile).where(
                RevenueEraFile.organization_id == organization.id,
                RevenueEraFile.sha256 == sha256,
            )
        ).scalar_one_or_none()
        if duplicate:
            _raise_phase2_error(
                status.HTTP_409_CONFLICT,
                error_code=ERROR_CODE_DUPLICATE,
                era_file_id=duplicate.id,
            )
        os.replace(temp_path, final_path)
        era_file = RevenueEraFile(
            id=file_id,
            organization_id=organization.id,
            file_name=safe_name,
            sha256=sha256,
            payer_name_raw=None,
            received_date=None,
            storage_ref=final_rel.as_posix(),
            status=STATUS_UPLOADED,
            error_detail=None,
        )
        db.add(era_file)
        db.flush()
        era_file_id = era_file.id
        record_processing_log(
            db,
            era_file_id=era_file.id,
            stage="UPLOAD",
            message=f"file_name={safe_name}",
            commit=False,
        )

        try:
            di_result = run_doc_intel(final_path)
            extracted_payload = di_result.get("extracted") or {}
            extract_row = RevenueEraExtractResult(
                id=str(uuid4()),
                era_file_id=era_file.id,
                extractor="azure_doc_intelligence",
                model_id=str(di_result.get("model_id", "")),
                extracted_json=extracted_payload,
            )
            db.add(extract_row)
            era_file.status = STATUS_EXTRACTED
            db.add(era_file)
            record_processing_log(
                db,
                era_file_id=era_file.id,
                stage="EXTRACTED",
                message=f"extractor={extract_row.extractor}; model_id={extract_row.model_id}",
                commit=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"extract_failed: {exc}") from exc

        try:
            structured = run_structuring_llm(extract_row.extracted_json)
            structured_row = RevenueEraStructuredResult(
                id=str(uuid4()),
                era_file_id=era_file.id,
                llm="azure_openai",
                deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip(),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "").strip(),
                prompt_version="era_structured_v1",
                structured_json=structured.model_dump(mode="json"),
            )
            db.add(structured_row)
            era_file.status = STATUS_STRUCTURED
            db.add(era_file)
            record_processing_log(
                db,
                era_file_id=era_file.id,
                stage="STRUCTURED",
                message=f"claim_count={len(structured.claim_lines)}",
                commit=False,
            )
        except ValidationError as exc:
            raise EraSchemaInvalidError(summarize_validation_error(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise EraSchemaInvalidError(str(exc)) from exc

        schema_valid = True
        phi_scan_passed, phi_hits = phi_scan(structured.model_dump(mode="json"))
        if not phi_scan_passed:
            raise EraPhiDetectedError("phi_detected")

        try:
            claim_count, work_count, _ = normalize_structured(db, era_file=era_file, structured=structured)
        except ValidationError as exc:
            raise EraSchemaInvalidError(summarize_validation_error(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"normalization_failed: {exc}") from exc

        recon = reconcile_era(structured)
        if not recon["reconciled"] and not recon["declared_total_missing"]:
            raise EraReconciliationError("declared_totals_mismatch")

        finalized = phi_scan_passed and schema_valid and (
            recon["reconciled"] or recon["declared_total_missing"]
        )
        report = RevenueEraValidationReport(
            id=str(uuid4()),
            org_id=organization.id,
            era_file_id=era_file.id,
            claim_count=claim_count,
            line_count=recon["line_count"],
            work_item_count=work_count,
            total_paid_cents=recon["total_paid_cents"],
            total_adjustment_cents=recon["total_adjustment_cents"],
            total_patient_resp_cents=recon["total_patient_resp_cents"],
            net_cents=recon["net_cents"],
            reconciled=recon["reconciled"],
            declared_total_missing=recon["declared_total_missing"],
            phi_scan_passed=phi_scan_passed,
            phi_hit_count=len(phi_hits),
            finalized=finalized,
        )
        db.add(report)
        era_file.status = STATUS_NORMALIZED
        if not era_file.payer_name_raw:
            era_file.payer_name_raw = structured.payer_name
        if not era_file.received_date and structured.received_date:
            era_file.received_date = structured.received_date
        db.add(era_file)
        record_processing_log(
            db,
            era_file_id=era_file.id,
            stage="NORMALIZED",
            message=(
                f"claim_count={claim_count}; work_item_count={work_count}; "
                f"reconciled={recon['reconciled']}; declared_total_missing={recon['declared_total_missing']}"
            ),
            commit=False,
        )
        db.commit()

        top_work_items = _top_work_items(db, organization_id=organization.id, era_file_id=file_id)
        return EraValidateResponse(
            era_file_id=file_id,
            reconciled=report.reconciled,
            declared_total_missing=report.declared_total_missing,
            claim_count=report.claim_count,
            line_count=report.line_count,
            work_item_count=report.work_item_count,
            totals_cents=ValidationTotalsResponse(
                paid=report.total_paid_cents,
                adjustment=report.total_adjustment_cents,
                patient_responsibility=report.total_patient_resp_cents,
                net=report.net_cents,
            ),
            top_work_items=top_work_items,
        )
    except HTTPException:
        if fail_closed:
            db.rollback()
        raise
    except EraSchemaInvalidError:
        if fail_closed:
            db.rollback()
        _raise_phase2_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code=ERROR_CODE_SCHEMA_INVALID,
            era_file_id=era_file_id,
        )
    except EraPhiDetectedError:
        if fail_closed:
            db.rollback()
        _raise_phase2_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code=ERROR_CODE_PHI_DETECTED,
            era_file_id=era_file_id,
        )
    except EraReconciliationError:
        if fail_closed:
            db.rollback()
        _raise_phase2_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code=ERROR_CODE_RECONCILIATION_FAILED,
            era_file_id=era_file_id,
        )
    except Exception:  # noqa: BLE001
        if fail_closed:
            db.rollback()
        _raise_phase2_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code=ERROR_CODE_PROCESSING_FAILED,
            era_file_id=era_file_id,
        )
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        if fail_closed and era_file_id and not db.get(RevenueEraFile, era_file_id):
            try:
                final_path.unlink(missing_ok=True)
            except Exception:
                pass


@router.get("/revenue/era-pdfs", response_model=list[EraFileResponse])
def list_era_pdfs(
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("billing:read")),
) -> list[EraFileResponse]:
    log_attempt(
        db,
        organization_id=organization.id,
        actor=membership.user.email,
        era_file_id="*",
        action="era_pdf_list",
    )
    rows = (
        db.execute(
            select(RevenueEraFile)
            .where(RevenueEraFile.organization_id == organization.id)
            .order_by(RevenueEraFile.created_at.desc())
            .limit(100)
        )
        .scalars()
        .all()
    )
    return rows


@router.post("/revenue/era-pdfs/{era_file_id}/process", response_model=EraFileResponse)
def process_era_pdf(
    era_file_id: str,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership: OrganizationMembership = Depends(get_current_membership),
    retry: bool = False,
    _: None = Depends(require_permission("billing:write")),
) -> EraFileResponse:
    timeout_seconds = 30

    def _locked_era_file() -> RevenueEraFile:
        row = (
            db.execute(
                select(RevenueEraFile)
                .where(
                    RevenueEraFile.id == era_file_id,
                    RevenueEraFile.organization_id == organization.id,
                )
                .with_for_update()
            )
            .scalar_one_or_none()
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="era_file_not_found")
        return row

    def _set_status(era_file: RevenueEraFile, new_status: str) -> None:
        if era_file.status == new_status:
            return
        allowed = {
            STATUS_UPLOADED: {STATUS_PROCESSING_EXTRACT, STATUS_ERROR},
            STATUS_PROCESSING_EXTRACT: {STATUS_PROCESSING_STRUCTURING, STATUS_ERROR},
            STATUS_PROCESSING_STRUCTURING: {STATUS_COMPLETE, STATUS_ERROR},
            STATUS_ERROR: {STATUS_UPLOADED},
            STATUS_COMPLETE: set(),
        }
        if new_status not in allowed.get(era_file.status, set()):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": "ERA_INVALID_STATE",
                    "era_file_id": era_file.id,
                    "current_status": era_file.status,
                },
            )
        era_file.status = new_status

    era_file = _locked_era_file()

    pdf_path = _repo_root() / era_file.storage_ref
    if not pdf_path.exists():
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="stored_pdf_missing")

    extract_row = _latest_extract_result(db, era_file.id)
    structured_row = _latest_structured_result(db, era_file.id)
    validation_report = _latest_validation_report(db, organization_id=organization.id, era_file_id=era_file.id)

    if era_file.status in {STATUS_PROCESSING_EXTRACT, STATUS_PROCESSING_STRUCTURING}:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "ERA_IN_PROGRESS",
                "era_file_id": era_file.id,
                "current_status": era_file.status,
            },
        )

    if era_file.status == STATUS_COMPLETE:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "ERA_ALREADY_COMPLETE",
                "era_file_id": era_file.id,
                "current_status": era_file.status,
            },
        )

    if era_file.status == STATUS_ERROR and not retry:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "ERA_INVALID_STATE",
                "era_file_id": era_file.id,
                "current_status": era_file.status,
                "retry_required": True,
                "has_extract_result": extract_row is not None,
                "has_structured_result": structured_row is not None,
                "finalized": validation_report.finalized if validation_report else None,
            },
        )

    if retry:
        if era_file.status != STATUS_ERROR or (validation_report is not None and validation_report.finalized):
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": "ERA_INVALID_STATE",
                    "era_file_id": era_file.id,
                    "current_status": era_file.status,
                    "retry_required": era_file.status == STATUS_ERROR,
                    "finalized": validation_report.finalized if validation_report else None,
                },
            )
        db.execute(delete(RevenueEraExtractResult).where(RevenueEraExtractResult.era_file_id == era_file.id))
        db.execute(delete(RevenueEraStructuredResult).where(RevenueEraStructuredResult.era_file_id == era_file.id))
        db.execute(delete(RevenueEraClaimLine).where(RevenueEraClaimLine.era_file_id == era_file.id))
        db.execute(delete(RevenueEraWorkItem).where(RevenueEraWorkItem.era_file_id == era_file.id))
        record_processing_log(
            db,
            era_file_id=era_file.id,
            stage="RETRY",
            message="event=retry_reset",
            commit=False,
        )
        _set_status(era_file, STATUS_UPLOADED)
        era_file.error_detail = None
        era_file.last_error_stage = None
        era_file.current_stage = None
        era_file.stage_started_at = None
        era_file.stage_completed_at = None
        db.add(era_file)
        db.commit()
        era_file = _locked_era_file()
        extract_row = None
        structured_row = None

    valid_statuses = {STATUS_UPLOADED, STATUS_EXTRACTED, STATUS_STRUCTURED, STATUS_ERROR}
    if era_file.status not in valid_statuses:
        _set_status(era_file, STATUS_ERROR)
        era_file.last_error_stage = "process"
        era_file.error_detail = "invalid_status"
        record_processing_log(db, era_file_id=era_file.id, stage="ERROR", message="invalid_status", commit=False)
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_status")

    def _fail(stage: str, message: str, http_status: int, detail: str) -> None:
        era_file = _locked_era_file()
        _set_status(era_file, STATUS_ERROR)
        era_file.last_error_stage = stage
        era_file.current_stage = stage
        if era_file.stage_started_at and era_file.stage_completed_at is None:
            era_file.stage_completed_at = utc_now()
        era_file.error_detail = message[:500]
        record_processing_log(db, era_file_id=era_file.id, stage="ERROR", message=message, commit=False)
        db.commit()
        raise HTTPException(status_code=http_status, detail=detail)

    def _run_with_timeout(func, *args):
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args)
            return future.result(timeout=timeout_seconds)

    def _exception_request_id(exc: Exception) -> str | None:
        request_id = getattr(exc, "request_id", None)
        if request_id:
            return str(request_id)
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
        if headers:
            return headers.get("x-ms-request-id") or headers.get("x-request-id")
        return None

    def _external_service_failure(stage: str, error_code: str, exc: Exception) -> JSONResponse:
        era_file = _locked_era_file()
        safe_error = {
            "error_code": error_code,
            "exception_type": exc.__class__.__name__,
            "stage": stage,
            "request_id": _exception_request_id(exc),
        }
        _set_status(era_file, STATUS_ERROR)
        era_file.last_error_stage = stage
        era_file.current_stage = stage
        if era_file.stage_started_at and era_file.stage_completed_at is None:
            era_file.stage_completed_at = utc_now()
        era_file.error_detail = json.dumps(safe_error, separators=(",", ":"), ensure_ascii=True)
        record_processing_log(
            db,
            era_file_id=era_file.id,
            stage=stage,
            message=f"error_code={error_code}; exception_type={safe_error['exception_type']}; request_id={safe_error['request_id'] or ''}",
            commit=False,
        )
        db.commit()
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": "external_service_failure", "stage": stage},
        )

    era_file.error_detail = None
    _set_status(era_file, STATUS_PROCESSING_EXTRACT)
    era_file.current_stage = "extract"
    era_file.stage_started_at = utc_now()
    era_file.stage_completed_at = None
    db.add(era_file)
    db.commit()
    era_file = _locked_era_file()

    try:
        di_result = _run_with_timeout(run_doc_intel, pdf_path)
    except (TimeoutError, FuturesTimeoutError, requests.exceptions.Timeout, httpx.TimeoutException) as exc:
        logger.error(
            "external_service_failure",
            extra={
                "stage": "extract",
                "era_file_id": era_file.id,
                "organization_id": organization.id,
                "error_code": "EXTRACT_TIMEOUT",
                "exception_type": exc.__class__.__name__,
                "request_id": _exception_request_id(exc),
            },
        )
        return _external_service_failure("extract", "EXTRACT_TIMEOUT", exc)
    except AzureError as exc:
        logger.error(
            "external_service_failure",
            extra={
                "stage": "extract",
                "era_file_id": era_file.id,
                "organization_id": organization.id,
                "error_code": "AZURE_ERROR",
                "exception_type": exc.__class__.__name__,
                "request_id": _exception_request_id(exc),
            },
        )
        return _external_service_failure("extract", "AZURE_ERROR", exc)
    except Exception as exc:
        logger.error(
            "external_service_failure",
            extra={
                "stage": "extract",
                "era_file_id": era_file.id,
                "organization_id": organization.id,
                "error_code": "UNKNOWN_ERROR",
                "exception_type": exc.__class__.__name__,
                "request_id": _exception_request_id(exc),
            },
        )
        return _external_service_failure("extract", "UNKNOWN_ERROR", exc)

    extracted_payload = di_result.get("extracted") or {}
    page_count = 0
    if isinstance(extracted_payload, dict):
        pages = extracted_payload.get("pages")
        if isinstance(pages, list):
            page_count = len(pages)

    era_file = _locked_era_file()
    db.execute(delete(RevenueEraExtractResult).where(RevenueEraExtractResult.era_file_id == era_file.id))
    extract_row = RevenueEraExtractResult(
        id=str(uuid4()),
        era_file_id=era_file.id,
        extractor="azure_doc_intelligence",
        model_id=str(di_result.get("model_id", "")),
        extracted_json=extracted_payload,
    )
    era_file.stage_completed_at = utc_now()
    db.add(extract_row)
    db.add(era_file)
    record_processing_log(
        db,
        era_file_id=era_file.id,
        stage="EXTRACTED",
        message=f"extractor={extract_row.extractor}; model_id={extract_row.model_id}; page_count={page_count}",
        commit=False,
    )
    db.commit()
    era_file = _locked_era_file()
    _set_status(era_file, STATUS_PROCESSING_STRUCTURING)
    era_file.current_stage = "structuring"
    era_file.stage_started_at = utc_now()
    era_file.stage_completed_at = None
    db.add(era_file)
    db.commit()
    era_file = _locked_era_file()

    structured: RevenueEraStructuredV1 | None = None
    if not extract_row:
        _fail("extract", "extract_missing", status.HTTP_400_BAD_REQUEST, "extract_missing")
    try:
        structured = _run_with_timeout(run_structuring_llm, extract_row.extracted_json)
    except ValidationError:
        _fail("structuring", "validation_failed", status.HTTP_422_UNPROCESSABLE_ENTITY, "structured_validation_failed")
    except (TimeoutError, FuturesTimeoutError, requests.exceptions.Timeout, httpx.TimeoutException) as exc:
        logger.error(
            "external_service_failure",
            extra={
                "stage": "structuring",
                "era_file_id": era_file.id,
                "organization_id": organization.id,
                "error_code": "STRUCTURE_TIMEOUT",
                "exception_type": exc.__class__.__name__,
                "request_id": _exception_request_id(exc),
            },
        )
        return _external_service_failure("structuring", "STRUCTURE_TIMEOUT", exc)
    except AzureError as exc:
        logger.error(
            "external_service_failure",
            extra={
                "stage": "structuring",
                "era_file_id": era_file.id,
                "organization_id": organization.id,
                "error_code": "AZURE_ERROR",
                "exception_type": exc.__class__.__name__,
                "request_id": _exception_request_id(exc),
            },
        )
        return _external_service_failure("structuring", "AZURE_ERROR", exc)
    except Exception as exc:
        logger.error(
            "external_service_failure",
            extra={
                "stage": "structuring",
                "era_file_id": era_file.id,
                "organization_id": organization.id,
                "error_code": "UNKNOWN_ERROR",
                "exception_type": exc.__class__.__name__,
                "request_id": _exception_request_id(exc),
            },
        )
        return _external_service_failure("structuring", "UNKNOWN_ERROR", exc)

    era_file = _locked_era_file()
    db.execute(delete(RevenueEraStructuredResult).where(RevenueEraStructuredResult.era_file_id == era_file.id))
    structured_row = RevenueEraStructuredResult(
        id=str(uuid4()),
        era_file_id=era_file.id,
        llm="azure_openai",
        deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip(),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "").strip(),
        prompt_version="era_structured_v1",
        structured_json=structured.model_dump(mode="json"),
    )
    db.add(structured_row)
    db.add(era_file)
    record_processing_log(
        db,
        era_file_id=era_file.id,
        stage="STRUCTURED",
        message=(
            f"llm={structured_row.llm}; deployment={structured_row.deployment}; "
            f"api_version={structured_row.api_version}; prompt_version={structured_row.prompt_version}; "
            f"claim_count={len(structured.claim_lines)}"
        ),
        commit=False,
    )

    if not structured:
        _fail("structuring", "structured_missing", status.HTTP_500_INTERNAL_SERVER_ERROR, "structuring_failed")

    try:
        with db.begin_nested():
            claim_count, work_count, dollars_total = normalize_structured(db, era_file=era_file, structured=structured)
            era_file.stage_completed_at = utc_now()
            _set_status(era_file, STATUS_COMPLETE)
            era_file.current_stage = "complete"
            if not era_file.payer_name_raw:
                era_file.payer_name_raw = structured.payer_name
            if not era_file.received_date and structured.received_date:
                era_file.received_date = structured.received_date
            db.add(era_file)
            record_processing_log(
                db,
                era_file_id=era_file.id,
                stage="NORMALIZED",
                message=(
                    f"claim_count={claim_count}; work_item_count={work_count}; dollars_cents_total={dollars_total}"
                ),
                commit=False,
            )
    except ValidationError:
        _fail("structuring", "validation_failed", status.HTTP_422_UNPROCESSABLE_ENTITY, "structured_validation_failed")
    except Exception:  # noqa: BLE001
        _fail("structuring", "normalization_failed", status.HTTP_500_INTERNAL_SERVER_ERROR, "normalization_failed")

    db.commit()
    db.refresh(era_file)
    final_row = era_file
    log_attempt(
        db,
        organization_id=organization.id,
        actor=membership.user.email,
        era_file_id=final_row.id,
        action="era_pdf_processed",
    )
    return final_row


@router.get("/revenue/era-pdfs/{era_file_id}/diagnostics", response_model=EraProcessDiagnosticsResponse)
def get_era_process_diagnostics(
    era_file_id: str,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("billing:read")),
) -> EraProcessDiagnosticsResponse:
    era_file = _era_file_or_404(db, era_file_id=era_file_id, organization_id=organization.id)
    extract_row = _latest_extract_result(db, era_file.id)
    structured_row = _latest_structured_result(db, era_file.id)
    validation_report = _latest_validation_report(db, organization_id=organization.id, era_file_id=era_file.id)
    last_error_code, last_error_stage = _safe_error_metadata(era_file.error_detail)
    log_attempt(
        db,
        organization_id=organization.id,
        actor=membership.user.email,
        era_file_id=era_file.id,
        action="era_pdf_process_diagnostics_view",
    )
    return EraProcessDiagnosticsResponse(
        era_file_id=era_file.id,
        current_status=era_file.status,
        current_stage=era_file.current_stage,
        stage_started_at=era_file.stage_started_at,
        stage_completed_at=era_file.stage_completed_at,
        retry_required=era_file.status == STATUS_ERROR,
        has_extract_result=extract_row is not None,
        has_structured_result=structured_row is not None,
        finalized=validation_report.finalized if validation_report else None,
        last_error_code=last_error_code,
        last_error_stage=era_file.last_error_stage or last_error_stage,
    )


@router.get("/revenue/era-worklist", response_model=list[WorkItemResponse])
def get_era_worklist(
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("billing:read")),
) -> list[WorkItemResponse]:
    rows = (
        db.execute(
            select(RevenueEraWorkItem)
            .where(
                RevenueEraWorkItem.organization_id == organization.id,
                RevenueEraWorkItem.status == WORKITEM_OPEN,
            )
            .order_by(RevenueEraWorkItem.dollars_cents.desc(), RevenueEraWorkItem.created_at.asc())
        )
        .scalars()
        .all()
    )
    log_attempt(
        db,
        organization_id=organization.id,
        actor=membership.user.email,
        era_file_id="*",
        action="era_worklist_view",
    )
    return rows


@router.get("/era/{era_file_id}/report", response_model=EraReportResponse)
def get_era_validation_report(
    era_file_id: str,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("billing:read")),
) -> EraReportResponse:
    _era_file_or_404(db, era_file_id=era_file_id, organization_id=organization.id)
    report = (
        db.execute(
            select(RevenueEraValidationReport).where(
                RevenueEraValidationReport.org_id == organization.id,
                RevenueEraValidationReport.era_file_id == era_file_id,
            )
        )
        .scalars()
        .first()
    )
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="era_report_not_found")
    top_work_items = _top_work_items(db, organization_id=organization.id, era_file_id=era_file_id)
    log_attempt(
        db,
        organization_id=organization.id,
        actor=membership.user.email,
        era_file_id=era_file_id,
        action="era_validation_report_view",
    )
    return EraReportResponse(
        era_file_id=report.era_file_id,
        claim_count=report.claim_count,
        line_count=report.line_count,
        work_item_count=report.work_item_count,
        total_paid_cents=report.total_paid_cents,
        total_adjustment_cents=report.total_adjustment_cents,
        total_patient_resp_cents=report.total_patient_resp_cents,
        net_cents=report.net_cents,
        reconciled=report.reconciled,
        declared_total_missing=report.declared_total_missing,
        phi_scan_passed=report.phi_scan_passed,
        phi_hit_count=report.phi_hit_count,
        finalized=report.finalized,
        created_at=report.created_at,
        top_work_items=top_work_items,
    )
