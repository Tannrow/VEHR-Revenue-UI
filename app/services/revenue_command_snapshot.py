from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db.models.claim import Claim, ClaimStatus
from app.db.models.claim_event import ClaimEvent, ClaimEventType
from app.db.models.claim_ledger import ClaimLedger
from app.db.models.revenue_command_snapshot import RevenueCommandSnapshot
from app.services.finance_intel.context_pack import CONTEXT_PACK_VERSION, _load_org_metrics, _load_payer_profile, _quantize
from app.services.finance_intel.payer_aggression import (
    AGGRESSION_SCORING_VERSION,
    compute_payer_aggression,
)

logger = logging.getLogger(__name__)

_ZERO = Decimal("0.00")
_PERCENT = Decimal("0.01")
_TEN_PERCENT = Decimal("0.10")
_TWENTY_PERCENT = Decimal("0.20")

RISK_SCORING_VERSION = CONTEXT_PACK_VERSION
PRE_SUBMISSION_SCORING_VERSION = "1.0"


def _to_decimal(value: Decimal | float | int | str | None) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return _ZERO


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class AggressivePayer:
    payer: str
    aggression_score: int
    aggression_tier: str
    aggression_drivers: list[str] = field(default_factory=list)

    def serialize(self) -> dict:
        return {
            "payer": self.payer,
            "aggression_score": int(self.aggression_score),
            "aggression_tier": self.aggression_tier,
            "aggression_drivers": list(self.aggression_drivers),
        }


@dataclass
class SnapshotComputationResult:
    generated_at: datetime
    org_id: str
    total_exposure: Decimal
    expected_recovery_30_day: Decimal
    short_term_cash_opportunity: Decimal
    high_risk_claim_count: int
    critical_pre_submission_count: int
    top_aggressive_payers: list[AggressivePayer]
    top_revenue_loss_drivers: list[str]
    worklist_priority_summary: dict
    execution_plan_30_day: list[dict]
    structural_moves_90_day: list[str]
    aggression_change_alerts: list[dict]
    risk_scoring_version: str = RISK_SCORING_VERSION
    aggression_scoring_version: str = AGGRESSION_SCORING_VERSION
    pre_submission_scoring_version: str = PRE_SUBMISSION_SCORING_VERSION

    def as_model_kwargs(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "org_id": self.org_id,
            "total_exposure": _quantize_money(self.total_exposure),
            "expected_recovery_30_day": _quantize_money(self.expected_recovery_30_day),
            "short_term_cash_opportunity": _quantize_money(self.short_term_cash_opportunity),
            "high_risk_claim_count": self.high_risk_claim_count,
            "critical_pre_submission_count": self.critical_pre_submission_count,
            "top_aggressive_payers": [payer.serialize() for payer in self.top_aggressive_payers],
            "top_revenue_loss_drivers": list(self.top_revenue_loss_drivers),
            "worklist_priority_summary": dict(self.worklist_priority_summary),
            "execution_plan_30_day": list(self.execution_plan_30_day),
            "structural_moves_90_day": list(self.structural_moves_90_day),
            "aggression_change_alerts": list(self.aggression_change_alerts),
            "risk_scoring_version": self.risk_scoring_version,
            "aggression_scoring_version": self.aggression_scoring_version,
            "pre_submission_scoring_version": self.pre_submission_scoring_version,
        }


def _load_aggressive_payers(db: Session, org_id: str) -> list[AggressivePayer]:
    payer_names: list[str] = (
        db.execute(
            select(func.distinct(Claim.payer_name))
            .where(Claim.org_id == org_id, Claim.payer_name.is_not(None))
            .order_by(Claim.payer_name.asc())
        )
        .scalars()
        .all()
    )
    if not payer_names:
        return []

    baseline = _load_payer_profile(db, org_id, payer_name=None)
    aggressive: list[AggressivePayer] = []
    for payer_name in payer_names:
        profile = _load_payer_profile(db, org_id, payer_name=payer_name)
        score = compute_payer_aggression(profile, baseline)
        aggressive.append(
            AggressivePayer(
                payer=payer_name or "Unknown",
                aggression_score=score.aggression_score,
                aggression_tier=score.aggression_tier,
                aggression_drivers=score.aggression_drivers,
            )
        )

    aggressive.sort(key=lambda item: item.aggression_score, reverse=True)
    return aggressive[:3]


def _count_high_risk_claims(db: Session, org_id: str) -> tuple[int, Decimal, dict]:
    rows = db.execute(
        select(
            ClaimLedger.total_billed,
            ClaimLedger.total_paid,
            ClaimLedger.variance,
            ClaimLedger.aging_days,
            Claim.status,
        ).join(Claim, Claim.id == ClaimLedger.claim_id)
        .where(Claim.org_id == org_id)
    ).all()

    high_risk = 0
    short_term_cash = _ZERO
    bucket_counts = {"high": 0, "medium": 0, "low": 0}

    for billed, paid, variance, aging_days, status in rows:
        billed_val = _to_decimal(billed)
        paid_val = _to_decimal(paid)
        variance_val = _to_decimal(variance)
        outstanding = _quantize_money((billed_val - paid_val) if billed_val else variance_val)
        aging = aging_days or 0
        status_str = status.value if isinstance(status, ClaimStatus) else str(status or "").upper()

        risky = aging > 90 or variance_val > (billed_val * _TEN_PERCENT) or status_str == ClaimStatus.DENIED.value
        if risky:
            high_risk += 1
            bucket_counts["high"] += 1
        elif aging > 60 or variance_val > (billed_val * _PERCENT * 5):
            bucket_counts["medium"] += 1
        else:
            bucket_counts["low"] += 1

        if aging <= 60 and outstanding > _ZERO:
            short_term_cash += outstanding

    return high_risk, _quantize_money(short_term_cash), bucket_counts


def _count_pre_submission_gaps(db: Session, org_id: str) -> int:
    missing_ledger = db.execute(
        select(func.count())
        .select_from(Claim)
        .outerjoin(ClaimLedger, Claim.id == ClaimLedger.claim_id)
        .where(Claim.org_id == org_id, ClaimLedger.id.is_(None))
    ).scalar_one()

    unacknowledged_events = db.execute(
        select(func.count())
        .select_from(ClaimEvent)
        .join(Claim, Claim.id == ClaimEvent.claim_id)
        .where(
            Claim.org_id == org_id,
            ClaimEvent.event_type.in_([ClaimEventType.SERVICE_RECORDED, ClaimEventType.ADJUSTMENT]),
        )
    ).scalar_one()

    return int(missing_ledger or 0) + int(unacknowledged_events or 0)


def _expected_recovery(total_exposure: Decimal, aging_buckets: dict[str, Decimal]) -> Decimal:
    recent = aging_buckets.get("0-30", _ZERO) + aging_buckets.get("31-60", _ZERO)
    tail = aging_buckets.get("61-90", _ZERO) + aging_buckets.get("91+", _ZERO)

    base_recovery = (recent * Decimal("0.55")) + (tail * Decimal("0.25"))
    if base_recovery > total_exposure:
        base_recovery = total_exposure
    return _quantize_money(base_recovery)


def _execution_plan(total_exposure: Decimal, short_term_cash: Decimal) -> list[dict]:
    return [
        {
            "title": "Clear aged denials and over-90 AR",
            "expected_impact": str(_quantize_money(total_exposure * Decimal("0.15"))),
            "owner": "Revenue Integrity",
            "priority": "high",
        },
        {
            "title": "Escalate aggressive payers with evidence packets",
            "expected_impact": str(_quantize_money(short_term_cash * Decimal("0.35"))),
            "owner": "Payer Ops",
            "priority": "medium",
        },
        {
            "title": "Triage pre-submission gaps",
            "expected_impact": str(_quantize_money(short_term_cash * Decimal("0.10"))),
            "owner": "Billing QA",
            "priority": "medium",
        },
    ]


def _structural_moves(total_exposure: Decimal) -> list[str]:
    return [
        "Tighten edit controls on recurring denial codes",
        "Bundle payer-specific policies into pre-submission templates",
        f"Allocate team capacity to claw back {_quantize_money(total_exposure * Decimal('0.05'))}",
    ]


def _detect_changes(previous: RevenueCommandSnapshot | None, current: SnapshotComputationResult) -> list[dict]:
    if previous is None:
        return []

    alerts: list[dict] = []

    prev_exposure = _to_decimal(previous.total_exposure)
    exposure_delta = current.total_exposure - prev_exposure
    if prev_exposure > _ZERO:
        exposure_pct = exposure_delta / prev_exposure
        if exposure_delta > Decimal("5000") and exposure_pct >= _TEN_PERCENT:
            alerts.append(
                {
                    "type": "exposure_increase",
                    "previous": str(_quantize_money(prev_exposure)),
                    "current": str(_quantize_money(current.total_exposure)),
                    "delta": str(_quantize_money(exposure_delta)),
                }
            )

    if current.high_risk_claim_count > previous.high_risk_claim_count:
        increase = current.high_risk_claim_count - previous.high_risk_claim_count
        if increase >= max(1, int(previous.high_risk_claim_count * 0.2)):
            alerts.append(
                {
                    "type": "high_risk_claim_spike",
                    "previous": previous.high_risk_claim_count,
                    "current": current.high_risk_claim_count,
                }
            )

    if current.critical_pre_submission_count > previous.critical_pre_submission_count:
        alerts.append(
            {
                "type": "pre_submission_trend",
                "previous": previous.critical_pre_submission_count,
                "current": current.critical_pre_submission_count,
            }
        )

    prev_payers = {}
    if isinstance(previous.top_aggressive_payers, Iterable):
        for entry in previous.top_aggressive_payers:
            try:
                payer = (entry.get("payer") if isinstance(entry, dict) else None) or ""
                score = int(entry.get("aggression_score")) if isinstance(entry, dict) else 0
                prev_payers[payer] = score
            except Exception:
                continue

    for payer in current.top_aggressive_payers:
        prev_score = prev_payers.get(payer.payer)
        if prev_score is not None and payer.aggression_score - prev_score >= 10:
            alerts.append(
                {
                    "type": "aggression_score_increase",
                    "payer": payer.payer,
                    "previous": prev_score,
                    "current": payer.aggression_score,
                }
            )
    if set(prev_payers.keys()) != {p.payer for p in current.top_aggressive_payers}:
        alerts.append({"type": "aggression_target_shift", "previous": sorted(prev_payers.keys()), "current": [p.payer for p in current.top_aggressive_payers]})

    return alerts


def compute_snapshot(db: Session, org_id: str, *, generated_at: datetime | None = None) -> SnapshotComputationResult:
    now = generated_at or utc_now()

    org_metrics = _load_org_metrics(db, org_id)
    total_exposure = _quantize(org_metrics.total_ar)

    high_risk_count, short_term_cash, worklist_buckets = _count_high_risk_claims(db, org_id)
    pre_submission_count = _count_pre_submission_gaps(db, org_id)
    aggressive_payers = _load_aggressive_payers(db, org_id)
    expected_recovery = _expected_recovery(total_exposure, org_metrics.aging_buckets)

    execution_plan = _execution_plan(total_exposure, short_term_cash)
    structural_moves = _structural_moves(total_exposure)

    return SnapshotComputationResult(
        generated_at=now,
        org_id=org_id,
        total_exposure=total_exposure,
        expected_recovery_30_day=expected_recovery,
        short_term_cash_opportunity=short_term_cash,
        high_risk_claim_count=high_risk_count,
        critical_pre_submission_count=pre_submission_count,
        top_aggressive_payers=aggressive_payers,
        top_revenue_loss_drivers=list(org_metrics.top_revenue_loss_drivers),
        worklist_priority_summary=worklist_buckets,
        execution_plan_30_day=execution_plan,
        structural_moves_90_day=structural_moves,
        aggression_change_alerts=[],
    )


def record_snapshot(db: Session, org_id: str, *, generated_at: datetime | None = None) -> RevenueCommandSnapshot:
    previous = (
        db.execute(
            select(RevenueCommandSnapshot)
            .where(RevenueCommandSnapshot.org_id == org_id)
            .order_by(RevenueCommandSnapshot.generated_at.desc())
            .limit(1)
        )
        .scalar_one_or_none()
    )

    computed = compute_snapshot(db, org_id, generated_at=generated_at)
    computed.aggression_change_alerts = _detect_changes(previous, computed)

    snapshot = RevenueCommandSnapshot(**computed.as_model_kwargs())
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def list_history(db: Session, org_id: str, *, limit: int = 30) -> list[RevenueCommandSnapshot]:
    rows = (
        db.execute(
            select(RevenueCommandSnapshot)
            .where(RevenueCommandSnapshot.org_id == org_id)
            .order_by(RevenueCommandSnapshot.generated_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return rows


def latest_snapshot(db: Session, org_id: str) -> RevenueCommandSnapshot | None:
    history = list_history(db, org_id, limit=1)
    return history[0] if history else None


def run_snapshot_job(db: Session, org_id: str) -> RevenueCommandSnapshot | None:
    start = time.perf_counter()
    try:
        snapshot = record_snapshot(db, org_id)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "revenue_command_snapshot_success",
            extra={"org_id": org_id, "snapshot_id": snapshot.id, "duration_ms": round(duration_ms, 2)},
        )
        return snapshot
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception("revenue_command_snapshot_failed org_id=%s duration_ms=%.2f", org_id, duration_ms)
        db.rollback()
        return None
