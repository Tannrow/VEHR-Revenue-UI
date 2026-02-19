from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db.models.claim import Claim, ClaimStatus
from app.db.models.claim_event import ClaimEvent, ClaimEventType
from app.db.models.claim_ledger import ClaimLedger
from app.db.models.claim_line import ClaimLine
from app.services.finance_intel.risk_scoring import RiskScore, score_context_pack

CONTEXT_PACK_VERSION = "2024.12.0"
_ZERO = Decimal("0.00")


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return _ZERO


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(_quantize(value))
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_value(val) for key, val in value.items()}
    if hasattr(value, "serialize"):
        return value.serialize()
    return value


@dataclass
class ClaimSnapshot:
    claim_id: str | None
    status: str | None
    billed_total: Decimal = _ZERO
    paid_total: Decimal = _ZERO
    allowed_total: Decimal = _ZERO
    variance_total: Decimal = _ZERO
    variance_pct: Decimal = _ZERO
    aging_days: int | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    lines: list[dict[str, Any]] = field(default_factory=list)

    def serialize(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "status": self.status,
            "billed_total": _serialize_value(self.billed_total),
            "paid_total": _serialize_value(self.paid_total),
            "allowed_total": _serialize_value(self.allowed_total),
            "variance_total": _serialize_value(self.variance_total),
            "variance_pct": _serialize_value(self.variance_pct),
            "aging_days": self.aging_days,
            "events": _serialize_value(self.events),
            "lines": _serialize_value(self.lines),
        }


@dataclass
class PayerProfile:
    payer_id: str | None
    denial_rate: Decimal = _ZERO
    underpay_rate: Decimal = _ZERO
    avg_delay_days: Decimal = _ZERO
    top_adjustment_codes: list[str] = field(default_factory=list)
    appeal_win_rate: Decimal = _ZERO

    def serialize(self) -> dict[str, Any]:
        return {
            "payer_id": self.payer_id,
            "denial_rate": _serialize_value(self.denial_rate),
            "underpay_rate": _serialize_value(self.underpay_rate),
            "avg_delay_days": _serialize_value(self.avg_delay_days),
            "top_adjustment_codes": list(self.top_adjustment_codes),
            "appeal_win_rate": _serialize_value(self.appeal_win_rate),
        }


@dataclass
class OrgMetrics:
    total_ar: Decimal = _ZERO
    aging_buckets: dict[str, Decimal] = field(default_factory=dict)
    top_revenue_loss_drivers: list[str] = field(default_factory=list)

    def serialize(self) -> dict[str, Any]:
        return {
            "total_ar": _serialize_value(self.total_ar),
            "aging_buckets": _serialize_value(self.aging_buckets),
            "top_revenue_loss_drivers": list(self.top_revenue_loss_drivers),
        }


@dataclass
class ContextPack:
    context_pack_version: str
    generated_at: datetime
    claim_snapshot: ClaimSnapshot | None
    payer_profile: PayerProfile
    org_metrics: OrgMetrics
    risk_score: RiskScore

    def serialize(self) -> dict[str, Any]:
        return {
            "context_pack_version": self.context_pack_version,
            "generated_at": self.generated_at.isoformat(),
            "claim_snapshot": self.claim_snapshot.serialize() if self.claim_snapshot else None,
            "payer_profile": self.payer_profile.serialize(),
            "org_metrics": self.org_metrics.serialize(),
            "risk_score": {
                "score": _serialize_value(self.risk_score.score),
                "tier": self.risk_score.tier,
                "rationale_tags": list(self.risk_score.rationale_tags),
            },
        }


def build_context_pack(session: Session, org_id: str, claim_id: str | None = None) -> ContextPack:
    snapshot, payer_name = _load_claim_snapshot(session, org_id, claim_id)
    payer_profile = _load_payer_profile(session, org_id, payer_name)
    org_metrics = _load_org_metrics(session, org_id)
    risk_score = score_context_pack(snapshot, payer_profile, org_metrics)

    return ContextPack(
        context_pack_version=CONTEXT_PACK_VERSION,
        generated_at=utc_now(),
        claim_snapshot=snapshot,
        payer_profile=payer_profile,
        org_metrics=org_metrics,
        risk_score=risk_score,
    )


def _load_claim_snapshot(session: Session, org_id: str, claim_id: str | None) -> tuple[ClaimSnapshot | None, str | None]:
    if not claim_id:
        return None, None

    stmt = (
        select(ClaimLedger, Claim)
        .join(Claim, Claim.id == ClaimLedger.claim_id)
        .where(ClaimLedger.claim_id == claim_id, ClaimLedger.org_id == org_id)
    )
    row = session.execute(stmt).first()
    payer_name: str | None = None
    billed_total = _ZERO
    paid_total = _ZERO
    allowed_total = _ZERO
    variance_total = _ZERO
    status: str | None = None
    aging_days: int | None = None

    if row:
        ledger, claim = row
        payer_name = claim.payer_name
        billed_total = _to_decimal(ledger.total_billed or _ZERO)
        paid_total = _to_decimal(ledger.total_paid or _ZERO)
        allowed_total = _to_decimal(ledger.total_allowed or _ZERO)
        variance_total = _to_decimal(ledger.variance if ledger.variance is not None else billed_total - paid_total)
        status = (ledger.status or claim.status).value if isinstance(ledger.status, ClaimStatus) else str(ledger.status)
        aging_days = ledger.aging_days
    else:
        claim_row = session.execute(
            select(Claim.status, Claim.payer_name).where(Claim.id == claim_id, Claim.org_id == org_id)
        ).first()
        if claim_row:
            status = claim_row.status.value if isinstance(claim_row.status, ClaimStatus) else str(claim_row.status)
            payer_name = claim_row.payer_name

    variance_pct = _ZERO
    if billed_total and billed_total != _ZERO:
        variance_pct = (variance_total / billed_total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    events = _load_claim_events(session, org_id, claim_id)
    lines = _load_claim_lines(session, org_id, claim_id)

    snapshot = ClaimSnapshot(
        claim_id=claim_id,
        status=status,
        billed_total=_quantize(billed_total),
        paid_total=_quantize(paid_total),
        allowed_total=_quantize(allowed_total),
        variance_total=_quantize(variance_total),
        variance_pct=variance_pct,
        aging_days=aging_days,
        events=events,
        lines=lines,
    )
    return snapshot, payer_name


def _load_claim_events(session: Session, org_id: str, claim_id: str) -> list[dict[str, Any]]:
    stmt = (
        select(ClaimEvent)
        .where(ClaimEvent.claim_id == claim_id, ClaimEvent.org_id == org_id)
        .order_by(ClaimEvent.event_date.desc().nullslast(), ClaimEvent.created_at.desc())
    )
    events: list[dict[str, Any]] = []
    for event in session.scalars(stmt):
        events.append(
            {
                "event_type": event.event_type.value if isinstance(event.event_type, ClaimEventType) else str(event.event_type),
                "event_date": event.event_date,
                "amount": _serialize_value(event.amount) if event.amount is not None else None,
            }
        )
    return events


def _load_claim_lines(session: Session, org_id: str, claim_id: str) -> list[dict[str, Any]]:
    stmt = (
        select(ClaimLine)
        .where(ClaimLine.claim_id == claim_id, ClaimLine.org_id == org_id)
        .order_by(ClaimLine.dos_from.desc().nullslast(), ClaimLine.created_at.desc())
    )
    lines: list[dict[str, Any]] = []
    for line in session.scalars(stmt):
        lines.append(
            {
                "cpt_code": line.cpt_code,
                "dos_from": line.dos_from,
                "units": _serialize_value(line.units) if line.units is not None else None,
                "billed_amount": _serialize_value(line.billed_amount) if line.billed_amount is not None else None,
                "expected_amount": _serialize_value(line.expected_amount) if line.expected_amount is not None else None,
            }
        )
    return lines


def _load_payer_profile(session: Session, org_id: str, payer_name: str | None) -> PayerProfile:
    base_filters = [Claim.org_id == org_id]
    if payer_name:
        base_filters.append(Claim.payer_name == payer_name)

    aggregates = session.execute(
        select(
            func.count().label("total_claims"),
            func.count().filter(ClaimLedger.status == ClaimStatus.DENIED).label("denied_claims"),
            func.count().filter(ClaimLedger.variance > 0).label("underpaying_claims"),
            func.avg(ClaimLedger.aging_days).label("avg_delay"),
        ).select_from(ClaimLedger).join(Claim, Claim.id == ClaimLedger.claim_id).where(*base_filters)
    ).one_or_none()

    total_claims = Decimal(str(aggregates.total_claims)) if aggregates and aggregates.total_claims else _ZERO
    denial_rate = _ZERO
    underpay_rate = _ZERO
    avg_delay_days = _ZERO

    if total_claims > _ZERO:
        denial_rate = _quantize(_to_decimal(aggregates.denied_claims) / total_claims) if aggregates else _ZERO
        underpay_rate = _quantize(_to_decimal(aggregates.underpaying_claims) / total_claims) if aggregates else _ZERO
        avg_delay_days = _quantize(_to_decimal(aggregates.avg_delay)) if aggregates and aggregates.avg_delay is not None else _ZERO

    decisions = session.execute(
        select(
            func.count().filter(ClaimEvent.event_type == ClaimEventType.PAYMENT).label("payments"),
            func.count().filter(ClaimEvent.event_type == ClaimEventType.DENIAL).label("denials"),
        )
        .select_from(ClaimEvent)
        .join(Claim, Claim.id == ClaimEvent.claim_id)
        .where(*base_filters)
    ).one_or_none()
    appeal_win_rate = _ZERO
    if decisions:
        total_decisions = (decisions.payments or 0) + (decisions.denials or 0)
        if total_decisions:
            appeal_win_rate = _quantize(_to_decimal(decisions.payments or 0) / Decimal(total_decisions))

    adjustment_codes: dict[str, int] = {}
    adjustment_stmt = (
        select(ClaimEvent.raw_json)
        .where(ClaimEvent.event_type == ClaimEventType.ADJUSTMENT)
        .join(Claim, Claim.id == ClaimEvent.claim_id)
        .where(*base_filters)
        .limit(100)
    )
    for row in session.execute(adjustment_stmt):
        raw = row.raw_json or {}
        if isinstance(raw, dict):
            code = raw.get("adjustment_code") or raw.get("code")
            if code:
                adjustment_codes[code] = adjustment_codes.get(code, 0) + 1
    top_adjustment_codes = sorted(adjustment_codes, key=adjustment_codes.get, reverse=True)[:3]

    return PayerProfile(
        payer_id=payer_name,
        denial_rate=denial_rate,
        underpay_rate=underpay_rate,
        avg_delay_days=avg_delay_days,
        top_adjustment_codes=top_adjustment_codes,
        appeal_win_rate=appeal_win_rate,
    )


def _load_org_metrics(session: Session, org_id: str) -> OrgMetrics:
    outstanding = func.coalesce(ClaimLedger.total_billed, 0) - func.coalesce(ClaimLedger.total_paid, 0)
    total_ar_value = session.execute(
        select(func.coalesce(func.sum(outstanding), 0)).select_from(ClaimLedger).join(Claim, Claim.id == ClaimLedger.claim_id).where(Claim.org_id == org_id)
    ).scalar_one()

    def bucket_sum(min_days: int | None, max_days: int | None) -> Decimal:
        filters = [Claim.org_id == org_id]
        if min_days is not None:
            filters.append(ClaimLedger.aging_days >= min_days)
        if max_days is not None:
            filters.append(ClaimLedger.aging_days <= max_days)
        value = session.execute(
            select(func.coalesce(func.sum(outstanding), 0))
            .select_from(ClaimLedger)
            .join(Claim, Claim.id == ClaimLedger.claim_id)
            .where(*filters)
        ).scalar_one()
        return _quantize(_to_decimal(value))

    aging_buckets = {
        "0-30": bucket_sum(0, 30),
        "31-60": bucket_sum(31, 60),
        "61-90": bucket_sum(61, 90),
        "91+": bucket_sum(91, None),
    }

    loss_stmt = (
        select(Claim.payer_name, func.coalesce(func.sum(ClaimLedger.variance), 0).label("loss"))
        .join(ClaimLedger, Claim.id == ClaimLedger.claim_id)
        .where(Claim.org_id == org_id)
        .group_by(Claim.payer_name)
        .order_by(func.coalesce(func.sum(ClaimLedger.variance), 0).desc())
        .limit(3)
    )
    loss_rows = session.execute(loss_stmt).all()
    top_revenue_loss_drivers = [
        row.payer_name or "Unspecified"
        for row in loss_rows
        if _to_decimal(row.loss) > _ZERO
    ]

    return OrgMetrics(
        total_ar=_quantize(_to_decimal(total_ar_value)),
        aging_buckets=aging_buckets,
        top_revenue_loss_drivers=top_revenue_loss_drivers,
    )
