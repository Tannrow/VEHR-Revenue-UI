from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, List
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, get_current_organization, require_permission
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.revenue_era import (
    RevenueEraExtractResult,
    RevenueEraFile,
    RevenueEraStructuredResult,
    RevenueEraWorkItem,
)
from app.db.session import get_db
from app.services.revenue_era import (
    STATUS_ERROR,
    STATUS_EXTRACTED,
    STATUS_NORMALIZED,
    STATUS_STRUCTURED,
    STATUS_UPLOADED,
    WORKITEM_OPEN,
    log_attempt,
    normalize_structured,
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
    era_file = (
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
    if not era_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="era_file_not_found")

    pdf_path = _repo_root() / era_file.storage_ref
    if not pdf_path.exists():
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="stored_pdf_missing")

    extract_row = _latest_extract_result(db, era_file.id)
    structured_row = _latest_structured_result(db, era_file.id)

    if era_file.status == STATUS_NORMALIZED:
        db.rollback()
        log_attempt(
            db,
            organization_id=organization.id,
            actor=membership.user.email,
            era_file_id=era_file.id,
            action="era_pdf_processed",
        )
        return era_file

    if era_file.status == STATUS_ERROR and not retry:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="retry_required")

    valid_statuses = {STATUS_UPLOADED, STATUS_EXTRACTED, STATUS_STRUCTURED, STATUS_ERROR}
    if era_file.status not in valid_statuses:
        era_file.status = STATUS_ERROR
        era_file.error_detail = "invalid_status"
        record_processing_log(db, era_file_id=era_file.id, stage="ERROR", message="invalid_status", commit=False)
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_status")

    def _fail(message: str, http_status: int, detail: str) -> None:
        era_file.status = STATUS_ERROR
        era_file.error_detail = message[:500]
        record_processing_log(db, era_file_id=era_file.id, stage="ERROR", message=message, commit=False)
        db.commit()
        raise HTTPException(status_code=http_status, detail=detail)

    era_file.error_detail = None

    if era_file.status in {STATUS_EXTRACTED, STATUS_STRUCTURED} and not extract_row:
        _fail("missing_extract_results", status.HTTP_500_INTERNAL_SERVER_ERROR, "extract_missing")

    if era_file.status in {STATUS_STRUCTURED} and not structured_row:
        _fail("missing_structured_results", status.HTTP_500_INTERNAL_SERVER_ERROR, "structuring_failed")

    if era_file.status in {STATUS_UPLOADED, STATUS_ERROR} and not extract_row:
        try:
            di_result = run_doc_intel(pdf_path)
        except HTTPException as exc:
            _fail(f"extract_failed: {exc.detail or exc}", exc.status_code, "extract_failed")
        except Exception as exc:
            _fail(f"extract_failed: {exc}", status.HTTP_502_BAD_GATEWAY, "doc_intelligence_failed")

        extracted_payload = di_result.get("extracted") or {}
        page_count = 0
        if isinstance(extracted_payload, dict):
            pages = extracted_payload.get("pages")
            if isinstance(pages, list):
                page_count = len(pages)

        db.execute(delete(RevenueEraExtractResult).where(RevenueEraExtractResult.era_file_id == era_file.id))
        extract_row = RevenueEraExtractResult(
            id=str(uuid4()),
            era_file_id=era_file.id,
            extractor="azure_doc_intelligence",
            model_id=str(di_result.get("model_id", "")),
            extracted_json=extracted_payload,
        )
        era_file.status = STATUS_EXTRACTED
        db.add(extract_row)
        db.add(era_file)
        record_processing_log(
            db,
            era_file_id=era_file.id,
            stage="EXTRACTED",
            message=f"extractor={extract_row.extractor}; model_id={extract_row.model_id}; page_count={page_count}",
            commit=False,
        )

    structured: RevenueEraStructuredV1 | None = None
    if structured_row and era_file.status in {STATUS_STRUCTURED, STATUS_EXTRACTED}:
        structured = RevenueEraStructuredV1.model_validate(structured_row.structured_json)
        era_file.status = STATUS_STRUCTURED
    else:
        if not extract_row:
            _fail("extract_missing", status.HTTP_400_BAD_REQUEST, "extract_missing")
        try:
            structured = run_structuring_llm(extract_row.extracted_json)
        except ValidationError as exc:
            detail = summarize_validation_error(exc)
            _fail(f"validation_failed: {detail}", status.HTTP_422_UNPROCESSABLE_ENTITY, "structured_validation_failed")
        except HTTPException as exc:
            _fail(f"structuring_failed: {exc.detail or exc}", exc.status_code, "structuring_failed")
        except Exception as exc:
            _fail(f"structuring_failed: {exc}", status.HTTP_502_BAD_GATEWAY, "structuring_failed")

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
        era_file.status = STATUS_STRUCTURED
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
        _fail("structured_missing", status.HTTP_500_INTERNAL_SERVER_ERROR, "structuring_failed")

    try:
        with db.begin_nested():
            claim_count, work_count, dollars_total = normalize_structured(db, era_file=era_file, structured=structured)
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
                    f"claim_count={claim_count}; work_item_count={work_count}; dollars_cents_total={dollars_total}"
                ),
                commit=False,
            )
    except ValidationError as exc:
        detail = summarize_validation_error(exc)
        _fail(f"validation_failed: {detail}", status.HTTP_422_UNPROCESSABLE_ENTITY, "structured_validation_failed")
    except Exception as exc:  # noqa: BLE001
        _fail(f"normalization_failed: {exc}", status.HTTP_500_INTERNAL_SERVER_ERROR, "normalization_failed")

    db.commit()
    log_attempt(
        db,
        organization_id=organization.id,
        actor=membership.user.email,
        era_file_id=era_file.id,
        action="era_pdf_processed",
    )
    return era_file


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
            .order_by(RevenueEraWorkItem.dollars_cents.desc())
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
