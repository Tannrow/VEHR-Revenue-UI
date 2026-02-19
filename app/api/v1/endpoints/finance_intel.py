from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership
from app.core.deps import require_permission  # noqa: F401
from app.db.models.organization_membership import OrganizationMembership
from app.db.session import get_db
from app.services.finance_intel.context_pack import _load_payer_profile
from app.services.finance_intel.payer_aggression import (
    AGGRESSION_SCORING_VERSION,
    PayerAggressionScore,
    compute_payer_aggression,
)

router = APIRouter(prefix="/intel", tags=["Finance Intel"])


class PayerAggressionResponse(BaseModel):
    payer_id: str | None
    aggression_score: int
    aggression_tier: str
    aggression_drivers: list[str]
    last_computed_at: datetime
    scoring_version: str

    model_config = {"extra": "forbid"}


def _set_read_only(db: Session) -> None:
    if db.bind and db.bind.dialect.name == "postgresql":
        try:
            db.execute(text("SET TRANSACTION READ ONLY"))
        except Exception:
            db.rollback()


@router.get("/payer-aggression", response_model=PayerAggressionResponse)
def get_payer_aggression(
    payer_id: str = Query(..., description="Payer identifier for aggression scoring"),
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> PayerAggressionResponse:
    if not payer_id.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="payer_id is required")

    _set_read_only(db)
    baseline_profile = _load_payer_profile(db, membership.organization_id, None)
    payer_profile = _load_payer_profile(db, membership.organization_id, payer_id)
    result: PayerAggressionScore = compute_payer_aggression(payer_profile, baseline_profile)
    db.rollback()
    return PayerAggressionResponse(
        payer_id=payer_profile.payer_id or payer_id,
        aggression_score=result.aggression_score,
        aggression_tier=result.aggression_tier,
        aggression_drivers=list(result.aggression_drivers),
        last_computed_at=result.last_computed_at,
        scoring_version=result.scoring_version or AGGRESSION_SCORING_VERSION,
    )
