from datetime import datetime
from decimal import Decimal

from app.services.finance_intel.context_pack import ClaimSnapshot, ContextPack, OrgMetrics, PayerProfile
from app.services.finance_intel.risk_scoring import RiskScore, score_context_pack


def test_risk_score_escalates_with_aging_variance_and_payer_history():
  snapshot = ClaimSnapshot(
    claim_id="c1",
    status="DENIED",
    billed_total=Decimal("1000.00"),
    paid_total=Decimal("100.00"),
    allowed_total=Decimal("0.00"),
    variance_total=Decimal("900.00"),
    variance_pct=Decimal("0.90"),
    aging_days=130,
  )
  payer_profile = PayerProfile(
    payer_id="payer-1",
    denial_rate=Decimal("0.25"),
    underpay_rate=Decimal("0.20"),
    avg_delay_days=Decimal("45.0"),
    top_adjustment_codes=[],
    appeal_win_rate=Decimal("0.10"),
  )
  org_metrics = OrgMetrics(total_ar=Decimal("500000.00"))

  risk = score_context_pack(snapshot, payer_profile, org_metrics)

  assert risk.tier == "HIGH"
  assert risk.score >= Decimal("70")
  assert "aging_gt_120" in risk.rationale_tags
  assert "variance_gt_10pct" in risk.rationale_tags
  assert "payer_underpay_history" in risk.rationale_tags


def test_context_pack_serializes_decimals_to_strings():
  snapshot = ClaimSnapshot(
    claim_id="c2",
    status="OPEN",
    billed_total=Decimal("100.10"),
    paid_total=Decimal("0.00"),
    allowed_total=Decimal("90.00"),
    variance_total=Decimal("10.10"),
    variance_pct=Decimal("0.10"),
    aging_days=15,
    events=[{"event_type": "PAYMENT", "amount": Decimal("5.00")}],
    lines=[{"billed_amount": Decimal("25.00")}],
  )
  payer_profile = PayerProfile(
    payer_id="payer-2",
    denial_rate=Decimal("0.05"),
    underpay_rate=Decimal("0.01"),
    avg_delay_days=Decimal("10"),
    top_adjustment_codes=["CO45"],
    appeal_win_rate=Decimal("0.50"),
  )
  org_metrics = OrgMetrics(
    total_ar=Decimal("1234.56"),
    aging_buckets={"0-30": Decimal("100.10")},
    top_revenue_loss_drivers=["payer-2"],
  )
  risk = RiskScore(score=Decimal("12.345"), tier="LOW", rationale_tags=["sample"]).quantized()
  pack = ContextPack(
    context_pack_version="v-test",
    generated_at=datetime(2024, 1, 1),
    claim_snapshot=snapshot,
    payer_profile=payer_profile,
    org_metrics=org_metrics,
    risk_score=risk,
  )

  serialized = pack.serialize()

  assert serialized["claim_snapshot"]["billed_total"] == "100.10"
  assert serialized["org_metrics"]["aging_buckets"]["0-30"] == "100.10"
  assert serialized["risk_score"]["score"] == "12.35"
  assert serialized["risk_score"]["tier"] == "LOW"
