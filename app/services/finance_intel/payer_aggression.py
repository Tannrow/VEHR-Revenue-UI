from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.core.time import utc_now
from app.services.finance_intel.context_pack import PayerProfile

AGGRESSION_SCORING_VERSION = "1.0"
AGGRESSION_SCORE_MAX = 100
BASELINE_DENIAL_THRESHOLD = Decimal("0.05")
UNDERPAY_THRESHOLD = Decimal("0.03")
DELAY_THRESHOLD_DAYS = Decimal("15")
DENY_THEN_PAY_DENIAL_DELTA = Decimal("0.10")
APPEAL_WIN_HIGH = Decimal("0.50")
VARIANCE_RATE_THRESHOLD = Decimal("0.05")
OUTCOME_RECOVERY_LOW = Decimal("0.35")
DENIAL_CLUSTER_THRESHOLD = Decimal("0.50")
AGING_TAIL_THRESHOLD = Decimal("0.10")

WEIGHT_DENIAL_RATE = 30
WEIGHT_UNDERPAY_RATE = 20
WEIGHT_DELAY = 15
WEIGHT_DENY_THEN_PAY = 10
WEIGHT_PARTIAL_RECOVERY = 10
WEIGHT_CLUSTER_TARGETING = 8
WEIGHT_AGING_SKEW = 12


@dataclass
class PayerAggressionScore:
    aggression_score: int
    aggression_tier: str
    aggression_drivers: list[str] = field(default_factory=list)
    last_computed_at: datetime = field(default_factory=utc_now)
    scoring_version: str = AGGRESSION_SCORING_VERSION


def _tier_for_score(score: int) -> str:
    if score >= 75:
        return "SEVERE"
    if score >= 50:
        return "HIGH"
    if score >= 25:
        return "MODERATE"
    return "LOW"


def compute_payer_aggression(
    profile: PayerProfile,
    org_baseline_metrics: PayerProfile | None = None,
) -> PayerAggressionScore:
    baseline = org_baseline_metrics or PayerProfile(
        payer_id=None,
        denial_rate=Decimal("0"),
        underpay_rate=Decimal("0"),
        avg_delay_days=Decimal("0"),
        top_adjustment_codes=[],
        appeal_win_rate=Decimal("0"),
        variance_rate=Decimal("0"),
        outcome_recovery_rate=Decimal("0"),
        denial_cluster_frequency=Decimal("0"),
        aging_tail_ratio=Decimal("0"),
    )

    score = 0
    drivers: list[str] = []

    denial_excess = profile.denial_rate > (baseline.denial_rate + BASELINE_DENIAL_THRESHOLD)
    if denial_excess:
        score += WEIGHT_DENIAL_RATE
        drivers.append("HIGH_DENIAL_RATE")

    underpay_excess = profile.underpay_rate > max(UNDERPAY_THRESHOLD, baseline.underpay_rate)
    if underpay_excess:
        score += WEIGHT_UNDERPAY_RATE
        drivers.append("HIGH_UNDERPAY_RATE")

    delay_excess = profile.avg_delay_days > (baseline.avg_delay_days + DELAY_THRESHOLD_DAYS)
    if delay_excess:
        score += WEIGHT_DELAY
        drivers.append("EXCESSIVE_PAYMENT_DELAY")

    deny_then_pay = denial_excess and profile.appeal_win_rate >= APPEAL_WIN_HIGH and profile.denial_rate > (
        baseline.denial_rate + DENY_THEN_PAY_DENIAL_DELTA
    )
    if deny_then_pay:
        score += WEIGHT_DENY_THEN_PAY
        drivers.append("DENY_THEN_PAY_PATTERN")

    partial_recovery_loop = profile.variance_rate > VARIANCE_RATE_THRESHOLD and profile.outcome_recovery_rate < OUTCOME_RECOVERY_LOW
    if partial_recovery_loop:
        score += WEIGHT_PARTIAL_RECOVERY
        drivers.append("PARTIAL_RECOVERY_LOOP")

    cluster_targeting = profile.denial_cluster_frequency > (baseline.denial_cluster_frequency + DENIAL_CLUSTER_THRESHOLD)
    if cluster_targeting:
        score += WEIGHT_CLUSTER_TARGETING
        drivers.append("CPT_CLUSTER_TARGETING")

    aging_skew = profile.aging_tail_ratio > (baseline.aging_tail_ratio + AGING_TAIL_THRESHOLD)
    if aging_skew:
        score += WEIGHT_AGING_SKEW
        drivers.append("AGING_DISTRIBUTION_SKEW")

    if score < 0:
        score = 0
    if score > AGGRESSION_SCORE_MAX:
        score = AGGRESSION_SCORE_MAX

    return PayerAggressionScore(
        aggression_score=int(score),
        aggression_tier=_tier_for_score(int(score)),
        aggression_drivers=drivers,
        last_computed_at=utc_now(),
        scoring_version=AGGRESSION_SCORING_VERSION,
    )
