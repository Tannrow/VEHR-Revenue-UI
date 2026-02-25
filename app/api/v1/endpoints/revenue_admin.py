"""
Revenue ERA admin endpoints – read-only inbox, exception view, detail,
reprocess, and export.

All routes require billing:read (or billing:write for reprocess)
and are organization-scoped.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, require_permission
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.revenue_era import (
    RevenueEraClaimLine,
    RevenueEraFile,
    RevenueEraProcessingLog,
    RevenueEraValidationReport,
    RevenueEraWorkItem,
)
from app.db.session import get_db
from app.services.revenue_era import STATUS_ERROR, STATUS_UPLOADED, log_attempt

router = APIRouter(prefix="/revenue/admin", tags=["Revenue Admin"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------

class AdminEraFileSummary(BaseModel):
    id: str
    file_name: str
    sha256: str
    status: str
    current_stage: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminInboxResponse(BaseModel):
    items: list[AdminEraFileSummary]
    status_counts: dict[str, int]


class AdminClaimLineResponse(BaseModel):
    id: int
    era_file_id: str
    line_index: int
    claim_ref: str
    match_status: str
    paid_cents: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminWorkItemResponse(BaseModel):
    id: str
    era_file_id: str
    type: str
    payer_name: str
    claim_ref: str
    dollars_cents: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminValidationReportResponse(BaseModel):
    id: str
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

    model_config = ConfigDict(from_attributes=True)


class AdminProcessingLogResponse(BaseModel):
    id: str
    era_file_id: str
    stage: str
    message: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminDetailResponse(BaseModel):
    era_file: AdminEraFileSummary
    claim_lines: list[AdminClaimLineResponse]
    work_items: list[AdminWorkItemResponse]
    latest_validation_report: AdminValidationReportResponse | None
    recent_processing_logs: list[AdminProcessingLogResponse]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _era_file_or_404(
    db: Session, *, era_file_id: str, organization_id: str
) -> RevenueEraFile:
    row = db.get(RevenueEraFile, era_file_id)
    if not row or row.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="era_file_not_found",
        )
    return row


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/inbox", response_model=AdminInboxResponse)
def admin_inbox(
    file_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("billing:read")),
) -> AdminInboxResponse:

    org_id = membership.organization_id

    q = select(RevenueEraFile).where(
        RevenueEraFile.organization_id == org_id
    )

    if file_status:
        q = q.where(RevenueEraFile.status == file_status)

    q = q.order_by(RevenueEraFile.created_at.desc()).limit(limit).offset(offset)
    items = db.execute(q).scalars().all()

    counts_rows = db.execute(
        select(RevenueEraFile.status, func.count().label("cnt"))
        .where(RevenueEraFile.organization_id == org_id)
        .group_by(RevenueEraFile.status)
    ).all()

    status_counts = {row.status: row.cnt for row in counts_rows}

    log_attempt(
        db,
        organization_id=org_id,
        actor=membership.user.email,
        era_file_id="*",
        action="admin_inbox_view",
    )

    return AdminInboxResponse(
        items=list(items),
        status_counts=status_counts,
    )


@router.get("/exceptions", response_model=list[AdminEraFileSummary])
def admin_exceptions(
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("billing:read")),
) -> list[AdminEraFileSummary]:

    org_id = membership.organization_id

    rows = (
        db.execute(
            select(RevenueEraFile)
            .where(
                RevenueEraFile.organization_id == org_id,
                RevenueEraFile.status == STATUS_ERROR,
            )
            .order_by(RevenueEraFile.created_at.desc())
        )
        .scalars()
        .all()
    )

    log_attempt(
        db,
        organization_id=org_id,
        actor=membership.user.email,
        era_file_id="*",
        action="admin_exceptions_view",
    )

    return list(rows)


@router.get("/era/{era_file_id}/detail", response_model=AdminDetailResponse)
def admin_era_detail(
    era_file_id: str,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("billing:read")),
) -> AdminDetailResponse:

    org_id = membership.organization_id
    era_file = _era_file_or_404(
        db, era_file_id=era_file_id, organization_id=org_id
    )

    claim_lines = (
        db.execute(
            select(RevenueEraClaimLine)
            .where(RevenueEraClaimLine.era_file_id == era_file_id)
            .order_by(RevenueEraClaimLine.line_index)
        )
        .scalars()
        .all()
    )

    work_items = (
        db.execute(
            select(RevenueEraWorkItem)
            .where(RevenueEraWorkItem.era_file_id == era_file_id)
            .order_by(RevenueEraWorkItem.created_at)
        )
        .scalars()
        .all()
    )

    latest_report = (
        db.execute(
            select(RevenueEraValidationReport)
            .where(
                RevenueEraValidationReport.org_id == org_id,
                RevenueEraValidationReport.era_file_id == era_file_id,
            )
            .order_by(RevenueEraValidationReport.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )

    recent_logs = (
        db.execute(
            select(RevenueEraProcessingLog)
            .where(RevenueEraProcessingLog.era_file_id == era_file_id)
            .order_by(RevenueEraProcessingLog.created_at.desc())
            .limit(20)
        )
        .scalars()
        .all()
    )

    log_attempt(
        db,
        organization_id=org_id,
        actor=membership.user.email,
        era_file_id=era_file_id,
        action="admin_era_detail_view",
    )

    return AdminDetailResponse(
        era_file=AdminEraFileSummary.model_validate(era_file),
        claim_lines=[
            AdminClaimLineResponse.model_validate(r) for r in claim_lines
        ],
        work_items=[
            AdminWorkItemResponse.model_validate(r) for r in work_items
        ],
        latest_validation_report=(
            AdminValidationReportResponse.model_validate(latest_report)
            if latest_report
            else None
        ),
        recent_processing_logs=[
            AdminProcessingLogResponse.model_validate(r)
            for r in recent_logs
        ],
    )


@router.post("/era/{era_file_id}/reprocess", response_model=AdminEraFileSummary)
def admin_reprocess_era(
    era_file_id: str,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("billing:write")),
) -> AdminEraFileSummary:

    org_id = membership.organization_id
    era_file = _era_file_or_404(
        db, era_file_id=era_file_id, organization_id=org_id
    )

    if era_file.status != STATUS_ERROR:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="era_file_not_in_error_state",
        )

    era_file.status = STATUS_UPLOADED
    era_file.current_stage = None
    era_file.stage_started_at = None
    era_file.stage_completed_at = None
    era_file.last_error_stage = None
    era_file.error_detail = None

    db.commit()
    db.refresh(era_file)

    log_attempt(
        db,
        organization_id=org_id,
        actor=membership.user.email,
        era_file_id=era_file_id,
        action="admin_era_reprocess",
    )

    return AdminEraFileSummary.model_validate(era_file)


@router.get("/era/{era_file_id}/export")
def admin_era_export(
    era_file_id: str,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("billing:read")),
) -> Any:

    org_id = membership.organization_id
    era_file = _era_file_or_404(
        db, era_file_id=era_file_id, organization_id=org_id
    )

    claim_lines = (
        db.execute(
            select(RevenueEraClaimLine)
            .where(RevenueEraClaimLine.era_file_id == era_file_id)
            .order_by(RevenueEraClaimLine.line_index)
        )
        .scalars()
        .all()
    )

    work_items = (
        db.execute(
            select(RevenueEraWorkItem)
            .where(RevenueEraWorkItem.era_file_id == era_file_id)
            .order_by(RevenueEraWorkItem.created_at)
        )
        .scalars()
        .all()
    )

    validation_reports = (
        db.execute(
            select(RevenueEraValidationReport)
            .where(
                RevenueEraValidationReport.org_id == org_id,
                RevenueEraValidationReport.era_file_id == era_file_id,
            )
            .order_by(RevenueEraValidationReport.created_at)
        )
        .scalars()
        .all()
    )

    processing_logs = (
        db.execute(
            select(RevenueEraProcessingLog)
            .where(RevenueEraProcessingLog.era_file_id == era_file_id)
            .order_by(RevenueEraProcessingLog.created_at)
        )
        .scalars()
        .all()
    )

    log_attempt(
        db,
        organization_id=org_id,
        actor=membership.user.email,
        era_file_id=era_file_id,
        action="admin_era_export",
    )

    return {
        "era_file": era_file,
        "claim_lines": claim_lines,
        "work_items": work_items,
        "validation_reports": validation_reports,
        "processing_logs": processing_logs,
    }
