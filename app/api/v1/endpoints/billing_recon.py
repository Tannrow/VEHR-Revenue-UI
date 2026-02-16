from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, require_permission
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.recon_claim_result import ReconClaimResult
from app.db.models.recon_import_job import ReconImportJob
from app.db.models.recon_line_result import ReconLineResult
from app.db.session import get_db
from app.services.audit import log_event


router = APIRouter(tags=["Billing Reconciliation"])

_ALLOWED_PDF_CONTENT_TYPES = {"application/pdf", "application/octet-stream"}


class ReconImportCreateResponse(BaseModel):
    job_id: str
    status: str
    duplicate: bool = False
    prior_job_id: str | None = None


class ReconImportStatusResponse(BaseModel):
    job_id: str
    status: str
    pages_detected_era: int | None = None
    tables_detected_era: int | None = None
    claims_extracted_era: int | None = None
    lines_extracted_era: int | None = None
    pages_detected_billed: int | None = None
    lines_extracted_billed: int | None = None
    skipped_counts_json: dict | None = None
    matched_claims: int | None = None
    unmatched_era_claims: int | None = None
    unmatched_billed_claims: int | None = None
    underpaid_claims: int | None = None
    denied_claims: int | None = None
    needs_review_claims: int | None = None
    output_xlsx_path: str | None = None
    error_message: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


class ReconClaimResultRead(BaseModel):
    id: int
    account_id: str | None = None
    match_status: str
    billed_total: float | None = None
    paid_total: float | None = None
    variance_total: float | None = None
    line_count: int | None = None
    reason_code: str | None = None


class ReconLineResultRead(BaseModel):
    id: int
    account_id: str | None = None
    dos_from: str | None = None
    dos_to: str | None = None
    proc_code: str | None = None
    billed_amount: float | None = None
    paid_amount: float | None = None
    variance_amount: float | None = None
    match_status: str
    reason_code: str | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _recon_upload_dir(org_id: str) -> Path:
    return _repo_root() / "uploads" / "recon" / org_id


def _sanitize_filename(filename: str | None) -> str:
    return Path(filename or "upload.pdf").name


def _is_pdf_upload(upload: UploadFile) -> bool:
    name_ok = _sanitize_filename(upload.filename).lower().endswith(".pdf")
    ctype = (upload.content_type or "").strip().lower()
    type_ok = ctype in _ALLOWED_PDF_CONTENT_TYPES
    return name_ok and type_ok


async def _write_upload_and_hash(upload: UploadFile, destination: Path) -> tuple[str, int]:
    sha = hashlib.sha256()
    total_bytes = 0
    first_chunk: bytes | None = None

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as out:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            if first_chunk is None:
                first_chunk = chunk[:8]
            out.write(chunk)
            sha.update(chunk)
            total_bytes += len(chunk)

    if total_bytes == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty_pdf_not_allowed")
    if first_chunk is None or not first_chunk.startswith(b"%PDF-"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_pdf_signature")

    return sha.hexdigest(), total_bytes


def _job_or_404(db: Session, *, org_id: str, job_id: str) -> ReconImportJob:
    row = db.execute(
        select(ReconImportJob).where(
            ReconImportJob.id == job_id,
            ReconImportJob.org_id == org_id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="recon_import_job_not_found")
    return row


def _as_float(value) -> float | None:
    return float(value) if value is not None else None


@router.post("/billing/recon/import", response_model=ReconImportCreateResponse)
async def create_recon_import_job(
    era_pdf: UploadFile = File(...),
    billed_pdf: UploadFile = File(...),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("billing:write")),
) -> ReconImportCreateResponse:
    if not _is_pdf_upload(era_pdf):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="era_pdf_must_be_pdf")
    if not _is_pdf_upload(billed_pdf):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="billed_pdf_must_be_pdf")

    org_id = membership.organization_id
    job_id = str(uuid4())
    upload_dir = _recon_upload_dir(org_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    era_final_rel = Path("uploads") / "recon" / org_id / f"{job_id}__era.pdf"
    billed_final_rel = Path("uploads") / "recon" / org_id / f"{job_id}__billed.pdf"
    era_temp = _repo_root() / f"{era_final_rel}.uploading"
    billed_temp = _repo_root() / f"{billed_final_rel}.uploading"

    try:
        era_sha256, era_size = await _write_upload_and_hash(era_pdf, era_temp)
        billed_sha256, billed_size = await _write_upload_and_hash(billed_pdf, billed_temp)

        duplicate = db.execute(
            select(ReconImportJob).where(
                ReconImportJob.org_id == org_id,
                ReconImportJob.status == "completed",
                ReconImportJob.era_sha256 == era_sha256,
                ReconImportJob.billed_sha256 == billed_sha256,
            )
        ).scalar_one_or_none()
        if duplicate:
            try:
                era_temp.unlink(missing_ok=True)
                billed_temp.unlink(missing_ok=True)
            except Exception:
                pass
            return ReconImportCreateResponse(
                job_id=duplicate.id,
                status="completed",
                duplicate=True,
                prior_job_id=duplicate.id,
            )

        era_final = _repo_root() / era_final_rel
        billed_final = _repo_root() / billed_final_rel
        os.replace(era_temp, era_final)
        os.replace(billed_temp, billed_final)

        row = ReconImportJob(
            id=job_id,
            org_id=org_id,
            uploaded_by_user_id=membership.user_id,
            status="queued",
            era_original_filename=_sanitize_filename(era_pdf.filename),
            era_storage_path=str(era_final_rel.as_posix()),
            era_sha256=era_sha256,
            billed_original_filename=_sanitize_filename(billed_pdf.filename),
            billed_storage_path=str(billed_final_rel.as_posix()),
            billed_sha256=billed_sha256,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        log_event(
            db,
            action="recon_import_queued",
            entity_type="recon_import_job",
            entity_id=row.id,
            organization_id=org_id,
            actor=membership.user.email,
            metadata={
                "job_id": row.id,
                "era_size_bytes": era_size,
                "billed_size_bytes": billed_size,
            },
        )

        return ReconImportCreateResponse(job_id=row.id, status=row.status, duplicate=False, prior_job_id=None)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="duplicate_pdf_hash_for_organization") from exc
    finally:
        try:
            await era_pdf.close()
        except Exception:
            pass
        try:
            await billed_pdf.close()
        except Exception:
            pass
        era_temp.unlink(missing_ok=True)
        billed_temp.unlink(missing_ok=True)


@router.get("/billing/recon/import/{job_id}", response_model=ReconImportStatusResponse)
def get_recon_import_job(
    job_id: str,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("billing:read")),
) -> ReconImportStatusResponse:
    row = _job_or_404(db, org_id=membership.organization_id, job_id=job_id)
    return ReconImportStatusResponse(
        job_id=row.id,
        status=row.status,
        pages_detected_era=row.pages_detected_era,
        tables_detected_era=row.tables_detected_era,
        claims_extracted_era=row.claims_extracted_era,
        lines_extracted_era=row.lines_extracted_era,
        pages_detected_billed=row.pages_detected_billed,
        lines_extracted_billed=row.lines_extracted_billed,
        skipped_counts_json=row.skipped_counts_json,
        matched_claims=row.matched_claims,
        unmatched_era_claims=row.unmatched_era_claims,
        unmatched_billed_claims=row.unmatched_billed_claims,
        underpaid_claims=row.underpaid_claims,
        denied_claims=row.denied_claims,
        needs_review_claims=row.needs_review_claims,
        output_xlsx_path=row.output_xlsx_path,
        error_message=row.error_message,
        created_at=row.created_at.isoformat(),
        started_at=row.started_at.isoformat() if row.started_at else None,
        finished_at=row.finished_at.isoformat() if row.finished_at else None,
    )


@router.get("/billing/recon/import/{job_id}/results")
def get_recon_import_results(
    job_id: str,
    level: Literal["claim", "line"] = Query(default="claim"),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("billing:read")),
) -> dict:
    _job_or_404(db, org_id=membership.organization_id, job_id=job_id)

    if level == "claim":
        rows = db.execute(
            select(ReconClaimResult)
            .where(
                ReconClaimResult.job_id == job_id,
                ReconClaimResult.org_id == membership.organization_id,
            )
            .order_by(ReconClaimResult.id.asc())
        ).scalars().all()
        return {
            "level": "claim",
            "count": len(rows),
            "rows": [
                ReconClaimResultRead(
                    id=row.id,
                    account_id=row.account_id,
                    match_status=row.match_status,
                    billed_total=_as_float(row.billed_total),
                    paid_total=_as_float(row.paid_total),
                    variance_total=_as_float(row.variance_total),
                    line_count=row.line_count,
                    reason_code=row.reason_code,
                ).model_dump()
                for row in rows
            ],
        }

    total = db.execute(
        select(func.count(ReconLineResult.id)).where(
            ReconLineResult.job_id == job_id,
            ReconLineResult.org_id == membership.organization_id,
        )
    ).scalar_one()
    rows = db.execute(
        select(ReconLineResult)
        .where(
            ReconLineResult.job_id == job_id,
            ReconLineResult.org_id == membership.organization_id,
        )
        .order_by(ReconLineResult.id.asc())
        .offset(offset)
        .limit(limit)
    ).scalars().all()
    return {
        "level": "line",
        "count": total,
        "offset": offset,
        "limit": limit,
        "rows": [
            ReconLineResultRead(
                id=row.id,
                account_id=row.account_id,
                dos_from=row.dos_from.isoformat() if row.dos_from else None,
                dos_to=row.dos_to.isoformat() if row.dos_to else None,
                proc_code=row.proc_code,
                billed_amount=_as_float(row.billed_amount),
                paid_amount=_as_float(row.paid_amount),
                variance_amount=_as_float(row.variance_amount),
                match_status=row.match_status,
                reason_code=row.reason_code,
            ).model_dump()
            for row in rows
        ],
    }


@router.get("/billing/recon/import/{job_id}/download")
def download_recon_import_output(
    job_id: str,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("billing:read")),
):
    row = _job_or_404(db, org_id=membership.organization_id, job_id=job_id)
    if not row.output_xlsx_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="recon_output_not_available")

    candidate = Path(row.output_xlsx_path)
    if not candidate.is_absolute():
        candidate = _repo_root() / candidate
    resolved = candidate.resolve()
    repo_root = _repo_root().resolve()
    if not str(resolved).startswith(str(repo_root)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid_output_path")
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="recon_output_missing")

    return FileResponse(
        path=str(resolved),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=resolved.name,
    )
