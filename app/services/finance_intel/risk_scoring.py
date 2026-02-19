from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.finance_intel.context_pack import ClaimSnapshot, OrgMetrics, PayerProfile

_ZERO = Decimal("0.00")


@dataclass
class RiskScore:
    score: Decimal
    tier: str
    rationale_tags: list[str] = field(default_factory=list)

    def quantized(self) -> RiskScore:
        return RiskScore(
            score=self.score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            tier=self.tier,
            rationale_tags=list(self.rationale_tags),
        )


def score_context_pack(
    snapshot: ClaimSnapshot | None,
    payer_profile: PayerProfile | None,
    org_metrics: OrgMetrics | None = None,
) -> RiskScore:
    score = _ZERO
    rationale: list[str] = []

    if snapshot:
        if snapshot.aging_days is not None:
            if snapshot.aging_days > 120:
                score += Decimal("35")
                rationale.append("aging_gt_120")
            elif snapshot.aging_days > 90:
                score += Decimal("25")
                rationale.append("aging_gt_90")
            elif snapshot.aging_days > 60:
                score += Decimal("15")
                rationale.append("aging_gt_60")
        if snapshot.variance_pct > Decimal("0.10"):
            score += Decimal("25")
            rationale.append("variance_gt_10pct")
        elif snapshot.variance_pct > Decimal("0.05"):
            score += Decimal("15")
            rationale.append("variance_gt_5pct")
        if (snapshot.status or "").upper() == "DENIED":
            score += Decimal("20")
            rationale.append("claim_denied")

    if payer_profile:
        if payer_profile.denial_rate > Decimal("0.20"):
            score += Decimal("15")
            rationale.append("payer_high_denial_rate")
        if payer_profile.underpay_rate > Decimal("0.15"):
            score += Decimal("15")
            rationale.append("payer_underpay_history")
        elif payer_profile.underpay_rate > Decimal("0.05"):
            score += Decimal("8")
            rationale.append("payer_some_underpay_history")
        if payer_profile.appeal_win_rate > _ZERO:
            score *= Decimal("1.00") - (payer_profile.appeal_win_rate * Decimal("0.20"))
            rationale.append("appeal_win_rate_adjustment")

    if org_metrics and org_metrics.total_ar > Decimal("250000"):
        score += Decimal("5")
        rationale.append("org_ar_load")

    if score < _ZERO:
        score = _ZERO
    if score > Decimal("100"):
        score = Decimal("100")

    tier = "LOW"
    if score >= Decimal("70"):
        tier = "HIGH"
    elif score >= Decimal("40"):
        tier = "MEDIUM"

    return RiskScore(score=score, tier=tier, rationale_tags=rationale).quantized()
