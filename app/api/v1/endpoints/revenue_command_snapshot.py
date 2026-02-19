from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, get_db
from app.core.rbac import ROLE_ADMIN, has_permission_for_organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.revenue_command_snapshot import RevenueCommandSnapshot
from app.services.revenue_command_snapshot import (
    PRE_SUBMISSION_SCORING_VERSION,
    RISK_SCORING_VERSION,
    latest_snapshot,
    list_history,
)

router = APIRouter(tags=["Revenue Command"])


def _serialize_decimal(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class ScoringVersions(BaseModel):
    risk_version: str
    aggression_version: str
    pre_submission_version: str

    model_config = ConfigDict(extra="forbid")


class RevenueCommandSnapshotRead(BaseModel):
    id: str
    generated_at: datetime
    org_id: str
    total_exposure: Decimal
    expected_recovery_30_day: Decimal
    short_term_cash_opportunity: Decimal
    high_risk_claim_count: int
    critical_pre_submission_count: int
    top_aggressive_payers: list[dict] = Field(default_factory=list)
    top_revenue_loss_drivers: list[str] = Field(default_factory=list)
    worklist_priority_summary: dict[str, Any] = Field(default_factory=dict)
    execution_plan_30_day: list[dict[str, Any]] = Field(default_factory=list)
    structural_moves_90_day: list[str] = Field(default_factory=list)
    aggression_change_alerts: list[dict[str, Any]] = Field(default_factory=list)
    scoring_versions: ScoringVersions

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        json_encoders={Decimal: _serialize_decimal},
    )


class RevenueCommandSummaryRequest(BaseModel):
    snapshot_id: UUID | None = None
    snapshot: RevenueCommandSnapshotRead | None = None

    model_config = ConfigDict(extra="forbid")


class RevenueCommandNarrative(BaseModel):
    headline: str
    cash_position: str
    risks: list[str] = Field(default_factory=list)
    execution_focus: list[str] = Field(default_factory=list)
    generated_from_snapshot_id: str | None = None
    scoring_versions: ScoringVersions

    model_config = ConfigDict(extra="forbid")


def _require_admin_or_exec(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> OrganizationMembership:
    allowed = membership.role == ROLE_ADMIN or has_permission_for_organization(
        db=db,
        organization_id=membership.organization_id,
        role=membership.role,
        permission="analytics:view",
    )
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return membership


def _to_read_model(snapshot: RevenueCommandSnapshot) -> RevenueCommandSnapshotRead:
    return RevenueCommandSnapshotRead(
        id=snapshot.id,
        generated_at=snapshot.generated_at,
        org_id=snapshot.org_id,
        total_exposure=snapshot.total_exposure,
        expected_recovery_30_day=snapshot.expected_recovery_30_day,
        short_term_cash_opportunity=snapshot.short_term_cash_opportunity,
        high_risk_claim_count=snapshot.high_risk_claim_count,
        critical_pre_submission_count=snapshot.critical_pre_submission_count,
        top_aggressive_payers=snapshot.top_aggressive_payers or [],
        top_revenue_loss_drivers=snapshot.top_revenue_loss_drivers or [],
        worklist_priority_summary=snapshot.worklist_priority_summary or {},
        execution_plan_30_day=snapshot.execution_plan_30_day or [],
        structural_moves_90_day=snapshot.structural_moves_90_day or [],
        aggression_change_alerts=snapshot.aggression_change_alerts or [],
        scoring_versions=ScoringVersions(
            risk_version=snapshot.risk_scoring_version or RISK_SCORING_VERSION,
            aggression_version=snapshot.aggression_scoring_version,
            pre_submission_version=snapshot.pre_submission_scoring_version or PRE_SUBMISSION_SCORING_VERSION,
        ),
    )


@router.get("/revenue/command/latest", response_model=RevenueCommandSnapshotRead)
def revenue_command_latest(
    membership: OrganizationMembership = Depends(_require_admin_or_exec),
    db: Session = Depends(get_db),
) -> RevenueCommandSnapshotRead:
    snapshot = latest_snapshot(db, membership.organization_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="snapshot_not_found")
    return _to_read_model(snapshot)


@router.get("/revenue/command/history", response_model=list[RevenueCommandSnapshotRead])
def revenue_command_history(
    membership: OrganizationMembership = Depends(_require_admin_or_exec),
    db: Session = Depends(get_db),
    limit: int = Query(default=30, ge=1, le=90),
) -> list[RevenueCommandSnapshotRead]:
    snapshots = list_history(db, membership.organization_id, limit=limit)
    return [_to_read_model(item) for item in snapshots]


def _load_snapshot_for_summary(
    payload: RevenueCommandSummaryRequest,
    membership: OrganizationMembership,
    db: Session,
) -> RevenueCommandSnapshotRead:
    if payload.snapshot:
        return payload.snapshot

    if payload.snapshot_id:
        snapshot = (
            db.query(RevenueCommandSnapshot)
            .filter(
                RevenueCommandSnapshot.id == str(payload.snapshot_id),
                RevenueCommandSnapshot.org_id == membership.organization_id,
            )
            .first()
        )
        if snapshot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="snapshot_not_found")
        return _to_read_model(snapshot)

    latest = latest_snapshot(db, membership.organization_id)
    if latest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="snapshot_not_found")
    return _to_read_model(latest)


@router.post("/ai/revenue-command-summary", response_model=RevenueCommandNarrative)
def revenue_command_summary(
    payload: RevenueCommandSummaryRequest,
    membership: OrganizationMembership = Depends(_require_admin_or_exec),
    db: Session = Depends(get_db),
) -> RevenueCommandNarrative:
    snapshot = _load_snapshot_for_summary(payload, membership, db)

    headline = (
        f"Exposure at {_serialize_decimal(snapshot.total_exposure)} with "
        f"expected 30d recovery of {_serialize_decimal(snapshot.expected_recovery_30_day)}."
    )
    risks: list[str] = []
    if snapshot.high_risk_claim_count:
        risks.append(f"{snapshot.high_risk_claim_count} high-risk claims require escalation.")
    if snapshot.critical_pre_submission_count:
        risks.append(f"{snapshot.critical_pre_submission_count} pre-submission gaps detected.")
    if snapshot.aggression_change_alerts:
        risks.append("Aggression shifts detected on key payers.")

    execution_focus = [
        "Prioritize over-90 AR cleanup.",
        "Escalate aggressive payer patterns with evidence packets.",
        "Close pre-submission gaps and stabilize edits.",
    ]

    return RevenueCommandNarrative(
        headline=headline,
        cash_position=_serialize_decimal(snapshot.short_term_cash_opportunity),
        risks=risks,
        execution_focus=execution_focus,
        generated_from_snapshot_id=snapshot.id,
        scoring_versions=snapshot.scoring_versions,
    )
