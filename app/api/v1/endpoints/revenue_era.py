from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
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
    run_doc_intel,
    run_structuring_llm,
    store_revenue_file,
    write_pdf_with_sha,
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


def _mark_error(db: Session, era_file: RevenueEraFile, message: str) -> None:
    db.rollback()
    era_file.status = STATUS_ERROR
    era_file.error_detail = message[:500]
    db.add(era_file)
    db.commit()


@router.post("/revenue/era-pdfs/upload", response_model=list[EraFileResponse])
async def upload_era_pdfs(
    files: list[UploadFile] = File(...),
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
    _: None = Depends(require_permission("billing:write")),
) -> EraFileResponse:
    era_file = _era_file_or_404(db, era_file_id=era_file_id, organization_id=organization.id)
    pdf_path = _repo_root() / era_file.storage_ref
    if not pdf_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="stored_pdf_missing")

    try:
        di_result = run_doc_intel(pdf_path)
        extract_row = RevenueEraExtractResult(
            id=str(uuid4()),
            era_file_id=era_file.id,
            extractor="azure_doc_intelligence",
            model_id=str(di_result.get("model_id", "")),
            extracted_json=di_result.get("extracted") or {},
        )
        era_file.status = STATUS_EXTRACTED
        era_file.error_detail = None
        db.add(extract_row)
        db.add(era_file)
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        _mark_error(db, era_file, f"extract_failed: {exc}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="doc_intelligence_failed") from exc

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
        era_file.status = STATUS_STRUCTURED
        db.add(structured_row)
        db.add(era_file)
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        _mark_error(db, era_file, f"structuring_failed: {exc}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="structuring_failed") from exc

    try:
        normalize_structured(db, era_file=era_file, structured=structured)
        era_file.status = STATUS_NORMALIZED
        if not era_file.payer_name_raw:
            era_file.payer_name_raw = structured.payer_name
        if not era_file.received_date and structured.received_date:
            era_file.received_date = structured.received_date
        db.add(era_file)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        _mark_error(db, era_file, f"normalization_failed: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="normalization_failed") from exc

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
