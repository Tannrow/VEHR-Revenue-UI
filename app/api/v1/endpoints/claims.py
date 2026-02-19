from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership
from app.db.models.claim import Claim, ClaimStatus
from app.db.models.claim_event import ClaimEvent, ClaimEventType
from app.db.models.claim_ledger import ClaimLedger
from app.db.session import get_db
from app.services.claim_ledger_service import ClaimLedgerService


router = APIRouter(prefix="/claims", tags=["Claims"])


class ClaimRead(BaseModel):
    id: str
    org_id: str
    external_claim_id: str | None = None
    patient_name: str | None = None
    member_id: str | None = None
    payer_name: str | None = None
    dos_from: date | None = None
    dos_to: date | None = None
    resubmission_count: int
    status: ClaimStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClaimLedgerRead(BaseModel):
    id: str
    claim_id: str
    org_id: str
    total_billed: Decimal | None = None
    total_paid: Decimal | None = None
    total_allowed: Decimal | None = None
    total_adjusted: Decimal | None = None
    variance: Decimal | None = None
    status: ClaimStatus
    aging_days: int | None = None
    last_event_date: date | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClaimEventRead(BaseModel):
    id: str
    claim_id: str
    org_id: str
    event_type: ClaimEventType
    event_date: date | None = None
    amount: Decimal | None = None
    job_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


def _get_claim_or_404(db: Session, claim_id: str, organization_id: str) -> Claim:
    claim = db.execute(
        select(Claim).where(
            Claim.id == claim_id,
            Claim.org_id == organization_id,
        )
    ).scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
    return claim


@router.get("", response_model=list[ClaimRead])
def list_claims(
    status_filter: ClaimStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    membership=Depends(get_current_membership),
) -> list[ClaimRead]:
    stmt = select(Claim).where(Claim.org_id == membership.organization_id)
    if status_filter:
        stmt = stmt.where(Claim.status == status_filter)
    claims = db.execute(stmt.order_by(Claim.created_at.desc()).limit(200)).scalars().all()
    return claims


@router.get("/{claim_id}", response_model=ClaimRead)
def get_claim(
    claim_id: str,
    db: Session = Depends(get_db),
    membership=Depends(get_current_membership),
) -> ClaimRead:
    claim = _get_claim_or_404(db, claim_id, membership.organization_id)
    return claim


@router.get("/{claim_id}/ledger", response_model=ClaimLedgerRead)
def get_claim_ledger(
    claim_id: str,
    db: Session = Depends(get_db),
    membership=Depends(get_current_membership),
) -> ClaimLedgerRead:
    _get_claim_or_404(db, claim_id, membership.organization_id)
    ledger = db.execute(
        select(ClaimLedger).where(
            ClaimLedger.claim_id == claim_id,
            ClaimLedger.org_id == membership.organization_id,
        )
    ).scalar_one_or_none()
    if ledger is None:
        ledger = ClaimLedgerService.compute_for_claim(db, claim_id)
    return ledger


@router.get("/{claim_id}/events", response_model=list[ClaimEventRead])
def get_claim_events(
    claim_id: str,
    db: Session = Depends(get_db),
    membership=Depends(get_current_membership),
) -> list[ClaimEventRead]:
    _get_claim_or_404(db, claim_id, membership.organization_id)
    events = db.execute(
        select(ClaimEvent)
        .where(
            ClaimEvent.claim_id == claim_id,
            ClaimEvent.org_id == membership.organization_id,
        )
        .order_by(ClaimEvent.created_at.asc())
    ).scalars().all()
    return events
