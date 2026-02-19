from decimal import Decimal

from app.services.finance_intel.context_pack import PayerProfile
from app.services.finance_intel.payer_aggression import (
    AGGRESSION_SCORING_VERSION,
    compute_payer_aggression,
)


def _baseline_profile() -> PayerProfile:
  return PayerProfile(
    payer_id=None,
    denial_rate=Decimal("0.10"),
    underpay_rate=Decimal("0.02"),
    avg_delay_days=Decimal("10"),
    top_adjustment_codes=[],
    appeal_win_rate=Decimal("0.40"),
    variance_rate=Decimal("0.02"),
    outcome_recovery_rate=Decimal("0.60"),
    denial_cluster_frequency=Decimal("0.30"),
    aging_tail_ratio=Decimal("0.05"),
  )


def test_aggression_score_caps_and_drivers_cover_all_components():
  baseline = _baseline_profile()
  profile = PayerProfile(
    payer_id="payer-max",
    denial_rate=Decimal("0.60"),
    underpay_rate=Decimal("0.20"),
    avg_delay_days=Decimal("40"),
    top_adjustment_codes=[],
    appeal_win_rate=Decimal("0.60"),
    variance_rate=Decimal("0.20"),
    outcome_recovery_rate=Decimal("0.10"),
    denial_cluster_frequency=Decimal("2.00"),
    aging_tail_ratio=Decimal("0.30"),
  )

  result = compute_payer_aggression(profile, baseline)

  assert result.aggression_score == 100  # capped at AGGRESSION_SCORE_MAX
  assert result.aggression_tier == "SEVERE"
  for tag in [
    "HIGH_DENIAL_RATE",
    "HIGH_UNDERPAY_RATE",
    "EXCESSIVE_PAYMENT_DELAY",
    "DENY_THEN_PAY_PATTERN",
    "PARTIAL_RECOVERY_LOOP",
    "CPT_CLUSTER_TARGETING",
    "AGING_DISTRIBUTION_SKEW",
  ]:
    assert tag in result.aggression_drivers


def test_tier_mapping_and_reproducibility():
  baseline = _baseline_profile()
  profile = PayerProfile(
    payer_id="payer-moderate",
    denial_rate=Decimal("0.18"),
    underpay_rate=Decimal("0.01"),
    avg_delay_days=Decimal("12"),
    top_adjustment_codes=[],
    appeal_win_rate=Decimal("0.10"),
    variance_rate=Decimal("0.01"),
    outcome_recovery_rate=Decimal("0.80"),
    denial_cluster_frequency=Decimal("0.10"),
    aging_tail_ratio=Decimal("0.06"),
  )

  first = compute_payer_aggression(profile, baseline)
  second = compute_payer_aggression(profile, baseline)

  assert first.aggression_score == second.aggression_score == 30
  assert first.aggression_tier == second.aggression_tier == "MODERATE"
  assert first.aggression_drivers == second.aggression_drivers == ["HIGH_DENIAL_RATE"]


def test_component_weights_are_isolated():
  baseline = _baseline_profile()
  profile = PayerProfile(
    payer_id="payer-underpay",
    denial_rate=Decimal("0.01"),
    underpay_rate=Decimal("0.06"),
    avg_delay_days=Decimal("5"),
    top_adjustment_codes=[],
    appeal_win_rate=Decimal("0.05"),
    variance_rate=Decimal("0.02"),
    outcome_recovery_rate=Decimal("0.90"),
    denial_cluster_frequency=Decimal("0.10"),
    aging_tail_ratio=Decimal("0.02"),
  )

  result = compute_payer_aggression(profile, baseline)

  assert result.aggression_score == 20
  assert result.aggression_drivers == ["HIGH_UNDERPAY_RATE"]
  assert result.aggression_tier == "LOW"


def test_version_and_types_are_explicit():
  baseline = _baseline_profile()
  profile = PayerProfile(
    payer_id="payer-types",
    denial_rate=Decimal("0.20"),
    underpay_rate=Decimal("0.04"),
    avg_delay_days=Decimal("40"),
    top_adjustment_codes=[],
    appeal_win_rate=Decimal("0.20"),
    variance_rate=Decimal("0.10"),
    outcome_recovery_rate=Decimal("0.10"),
    denial_cluster_frequency=Decimal("0.90"),
    aging_tail_ratio=Decimal("0.40"),
  )

  result = compute_payer_aggression(profile, baseline)

  assert isinstance(result.aggression_score, int)
  assert result.scoring_version == AGGRESSION_SCORING_VERSION
  assert isinstance(result.aggression_drivers, list)
  assert result.aggression_tier in {"LOW", "MODERATE", "HIGH", "SEVERE"}
