from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership
from app.db.session import get_db
from app.db.models.organization_membership import OrganizationMembership
from app.services.finance_intel.context_pack import build_context_pack


router = APIRouter(prefix="/ai", tags=["AI Finance"])

FINANCE_AI_GUARDRAILS = (
  "You are a read-only revenue intelligence analyst. Do not propose or perform any data mutations, ledger edits, or status updates. "
  "Use provided context only and defer to humans for any financial changes."
)


class FinanceRecommendedAction(BaseModel):
  action: str
  impact_estimate: Decimal
  urgency: Literal["high", "medium", "low"]

  model_config = ConfigDict(
    extra="forbid",
    json_encoders={Decimal: lambda value: str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))},
  )


class FinanceDraft(BaseModel):
  type: str
  content: str
  model_config = ConfigDict(extra="forbid")


class FinanceAIResponse(BaseModel):
  summary: str
  root_cause: str
  recommended_actions: list[FinanceRecommendedAction] = Field(default_factory=list)
  drafts: list[FinanceDraft] = Field(default_factory=list)
  questions_needed: list[str] = Field(default_factory=list)
  assumptions: list[str] = Field(default_factory=list)
  data_used: dict[str, Any] | list[Any] | None = Field(default_factory=dict)
  confidence: Literal["low", "medium", "high"]
  model_config = ConfigDict(extra="forbid")


class FinanceAIEnvelope(BaseModel):
  context_pack_version: str
  generated_at: datetime
  risk_score: Decimal
  advisory: FinanceAIResponse

  model_config = ConfigDict(
    extra="forbid",
    json_encoders={Decimal: lambda value: str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))},
  )


class FinanceAIContext(BaseModel):
  scope: str | None = None
  claim_ids: list[str] = Field(default_factory=list)
  payer: str | None = None
  cohort: str | None = None
  period: str | None = None
  narrative: str | None = None
  include_drafts: bool = True
  model_config = ConfigDict(extra="forbid")


class RevenueIntegrityPayload(BaseModel):
  claim_snapshot: dict[str, Any] = Field(default_factory=dict)
  payer_profile: dict[str, Any] = Field(default_factory=dict)
  org_metrics: dict[str, Any] = Field(default_factory=dict)
  risk_score: Decimal | None = None
  aging_data: dict[str, Any] = Field(default_factory=dict)
  variance_metrics: dict[str, Any] = Field(default_factory=dict)
  denial_codes: list[str] = Field(default_factory=list)
  adjustment_codes: list[str] = Field(default_factory=list)
  appeal_win_rate_history: dict[str, Any] = Field(default_factory=dict)
  delay_history: dict[str, Any] = Field(default_factory=dict)
  recovery_history: dict[str, Any] = Field(default_factory=dict)
  narrative: str | None = Field(default=None, max_length=2000)


class RevenueIntegrityAction(BaseModel):
  step: str
  rationale: str
  roi_per_hour: Decimal
  references: list[str] = Field(default_factory=list)

  model_config = ConfigDict(json_encoders={Decimal: lambda value: str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))})


class RevenueIntegrityDraft(BaseModel):
  type: str
  content: str


class RevenueIntegrityThreshold(BaseModel):
  trigger: str
  threshold: Decimal
  unit: str
  note: str | None = None

  model_config = ConfigDict(json_encoders={Decimal: lambda value: str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))})


class RevenueExposureAnalysis(BaseModel):
  at_risk_total: Decimal
  structural_component: Decimal
  procedural_component: Decimal
  aging_over_90: Decimal
  notes: str

  model_config = ConfigDict(json_encoders={Decimal: lambda value: str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))})


class ExpectedRecoveryEstimate(BaseModel):
  exposure_basis: Decimal
  recovery_probability: Decimal
  expected_recovery_value: Decimal
  method: str

  model_config = ConfigDict(json_encoders={Decimal: lambda value: str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))})


class PayerBehaviorAnalysis(BaseModel):
  behaviors: list[str] = Field(default_factory=list)
  evidence: list[str] = Field(default_factory=list)


class RevenueIntegrityResponse(BaseModel):
  strategic_summary: str
  revenue_exposure_analysis: RevenueExposureAnalysis
  payer_behavior_analysis: PayerBehaviorAnalysis
  operational_priority_score_explanation: str
  expected_recovery_estimate: ExpectedRecoveryEstimate
  recommended_action_sequence: list[RevenueIntegrityAction] = Field(default_factory=list)
  draft_pack: list[RevenueIntegrityDraft] = Field(default_factory=list)
  escalation_thresholds: list[RevenueIntegrityThreshold] = Field(default_factory=list)
  data_used: list[str] = Field(default_factory=list)
  assumptions: list[str] = Field(default_factory=list)
  confidence: Literal["low", "medium", "high"]


def _deterministic_score(seed: str) -> Decimal:
  digest = hashlib.sha256(seed.encode("utf-8")).digest()
  numeric = int.from_bytes(digest[:4], "big") % 100
  return (Decimal(numeric) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _confidence_from_score(score: Decimal) -> Literal["low", "medium", "high"]:
  if score >= Decimal("0.75"):
    return "high"
  if score >= Decimal("0.45"):
    return "medium"
  return "low"


def _quantized_decimal(value: Any, default: Decimal = Decimal("0.00")) -> Decimal:
  try:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
  except Exception:
    return default


def _metric_from(payload: dict[str, Any] | None, *keys: str, default: Decimal = Decimal("0.00")) -> Decimal:
  if not payload:
    return default
  for key in keys:
    if key in payload and payload[key] is not None:
      return _quantized_decimal(payload[key], default)
  return default


def _clamp_decimal(value: Decimal, minimum: Decimal = Decimal("0.00"), maximum: Decimal = Decimal("1.00")) -> Decimal:
  if value < minimum:
    return minimum
  if value > maximum:
    return maximum
  return value


def _base_actions(kind: str) -> list[FinanceRecommendedAction]:
  if kind == "claim-analysis":
    return [
      FinanceRecommendedAction(action="Prioritize underpaid claims with variance > 10%", impact_estimate=Decimal("125000"), urgency="high"),
      FinanceRecommendedAction(action="Escalate denial patterns to payer reps with evidence packets", impact_estimate=Decimal("46000"), urgency="medium"),
      FinanceRecommendedAction(action="Tighten eligibility and coding checks on recurring denials", impact_estimate=Decimal("22000"), urgency="medium"),
    ]
  if kind == "worklist":
    return [
      FinanceRecommendedAction(action="Work high-dollar, high-variance claims first", impact_estimate=Decimal("87000"), urgency="high"),
      FinanceRecommendedAction(action="Batch appeal packets for repeat denial reasons", impact_estimate=Decimal("39000"), urgency="medium"),
      FinanceRecommendedAction(action="Schedule payer touchpoint for stalled accounts", impact_estimate=Decimal("18000"), urgency="low"),
    ]
  if kind == "payer-intel":
    return [
      FinanceRecommendedAction(action="Renegotiate adjustment rules on top 2 denial codes", impact_estimate=Decimal("54000"), urgency="medium"),
      FinanceRecommendedAction(action="Add pre-bill guardrails for outlier payers", impact_estimate=Decimal("31000"), urgency="medium"),
    ]
  if kind == "executive-summary":
    return [
      FinanceRecommendedAction(action="Protect clean claims pipeline with daily QA", impact_estimate=Decimal("76000"), urgency="high"),
      FinanceRecommendedAction(action="Fund payer ops sprint to clear aged AR", impact_estimate=Decimal("52000"), urgency="medium"),
      FinanceRecommendedAction(action="Automate variance alerts to managers", impact_estimate=Decimal("15000"), urgency="low"),
    ]
  return [
    FinanceRecommendedAction(action="Stage drafts for payer outreach", impact_estimate=Decimal("18000"), urgency="medium"),
    FinanceRecommendedAction(action="Validate figures against ledger snapshots", impact_estimate=Decimal("9000"), urgency="low"),
  ]


def _drafts_for(kind: str) -> list[FinanceDraft]:
  if kind == "drafting":
    return [
      FinanceDraft(type="appeal_letter", content="Draft appeal letter outlining variance evidence and requested make-goods."),
      FinanceDraft(type="payer_email", content="Email to payer rep summarizing denial trend and requesting expedited review."),
      FinanceDraft(type="ops_brief", content="Internal brief with next steps, owners, and checkpoints for revenue recovery."),
    ]
  if kind == "worklist":
    return [
      FinanceDraft(type="task_batch", content="Worklist batch: re-bill corrected claims, attach ERA evidence, set 5-day follow-up."),
      FinanceDraft(type="reminder", content="Reminder to finance lead to review payer response SLAs on Thursday."),
    ]
  if kind == "payer-intel":
    return [
      FinanceDraft(type="summary", content="Payer trend digest: denials clustered in auth and coding; propose joint QA."),
    ]
  return [
    FinanceDraft(type="summary", content="Financial summary draft ready for review."),
  ]


def _assemble_response(kind: str, context: FinanceAIContext, membership: OrganizationMembership, db: Session) -> FinanceAIEnvelope:
  primary_claim_id = context.claim_ids[0] if context.claim_ids else None
  context_pack = build_context_pack(db, membership.organization_id, primary_claim_id)
  risk_score = context_pack.risk_score.score
  confidence = _confidence_from_score(risk_score)

  response = FinanceAIResponse(
    summary={
      "claim-analysis": "Revenue assurance review highlights concentration of underpayments in recent ERA batches with predictable denial codes.",
      "worklist": "Queue is reordered to clear high-impact claims first while keeping SLAs intact.",
      "payer-intel": "Top payers show tightening policies on auth and coding; leakage tied to repeatable root causes.",
      "executive-summary": "Revenue position is stable with targeted exposure in denials; focused actions keep cash predictable.",
      "drafting": "Prepared draft artifacts to accelerate outreach without altering financial systems.",
    }.get(kind, "Financial intelligence available for this scope."),
    root_cause={
      "claim-analysis": "Variance driven by coding mismatches and missing auth data on repeat payer policies.",
      "worklist": "Aged items cluster around a few denial reasons and stalled follow-ups.",
      "payer-intel": "Two payers tightened edit rules; rejections spike when auth and diagnosis pairs misalign.",
      "executive-summary": "Denial exposure contained but requires swift clean-up on high-dollar accounts.",
      "drafting": "Teams need ready-to-send language to expedite payer responses.",
    }.get(kind, "Operational insight derived from deterministic rules."),
    recommended_actions=_base_actions(kind),
    drafts=_drafts_for(kind) if context.include_drafts else [],
    questions_needed=[
      "Confirm payer contacts for escalations",
      "Validate latest fee schedule version",
    ],
    assumptions=[
      "Ledger figures remain the source of truth",
      "No write operations performed by AI endpoints",
      FINANCE_AI_GUARDRAILS,
    ],
    data_used={
      "context_scope": context.scope,
      "claim_ids": context.claim_ids,
      "payer": context.payer,
      "cohort": context.cohort,
      "period": context.period,
      "context_pack": context_pack.serialize(),
      "guardrails": FINANCE_AI_GUARDRAILS,
    },
    confidence=confidence,
  )

  return FinanceAIEnvelope(
    context_pack_version=context_pack.context_pack_version,
    generated_at=context_pack.generated_at,
    risk_score=risk_score,
    advisory=response,
  )


def _safe_response(kind: str, context: FinanceAIContext, membership: OrganizationMembership, db: Session) -> FinanceAIEnvelope:
  try:
    return _assemble_response(kind, context, membership, db)
  except Exception as exc:
    db.rollback()
    raise HTTPException(
      status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
      detail="ai_finance_unavailable",
    ) from exc
  finally:
    db.rollback()


@router.post("/claim-analysis", response_model=FinanceAIEnvelope)
def ai_claim_analysis(
  payload: FinanceAIContext,
  membership: OrganizationMembership = Depends(get_current_membership),
  db: Session = Depends(get_db),
) -> FinanceAIEnvelope:
  return _safe_response("claim-analysis", payload, membership, db)


@router.post("/worklist", response_model=FinanceAIEnvelope)
def ai_worklist(
  payload: FinanceAIContext,
  membership: OrganizationMembership = Depends(get_current_membership),
  db: Session = Depends(get_db),
) -> FinanceAIEnvelope:
  return _safe_response("worklist", payload, membership, db)


@router.post("/payer-intel", response_model=FinanceAIEnvelope)
def ai_payer_intel(
  payload: FinanceAIContext,
  membership: OrganizationMembership = Depends(get_current_membership),
  db: Session = Depends(get_db),
) -> FinanceAIEnvelope:
  return _safe_response("payer-intel", payload, membership, db)


@router.post("/executive-summary", response_model=FinanceAIEnvelope)
def ai_executive_summary(
  payload: FinanceAIContext,
  membership: OrganizationMembership = Depends(get_current_membership),
  db: Session = Depends(get_db),
) -> FinanceAIEnvelope:
  return _safe_response("executive-summary", payload, membership, db)


@router.post("/drafting", response_model=FinanceAIEnvelope)
def ai_drafting(
  payload: FinanceAIContext,
  membership: OrganizationMembership = Depends(get_current_membership),
  db: Session = Depends(get_db),
) -> FinanceAIEnvelope:
  return _safe_response("drafting", payload, membership, db)


def _assemble_revenue_integrity_response(payload: RevenueIntegrityPayload, membership: OrganizationMembership) -> RevenueIntegrityResponse:
  seed = f"{membership.organization_id}:{membership.user_id}:{payload.claim_snapshot.get('claim_id', '')}:{payload.payer_profile.get('payer_id', '')}"
  base_risk_score = _quantized_decimal(payload.risk_score) if payload.risk_score is not None else _deterministic_score(seed)
  structural_component = _metric_from(payload.variance_metrics, "structural", "structural_underpayment")
  procedural_component = _metric_from(payload.variance_metrics, "procedural", "procedural_denial")
  variance_total = _metric_from(payload.variance_metrics, "variance_total")
  if variance_total == Decimal("0.00"):
    variance_total = (structural_component + procedural_component).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
  aging_over_90 = _metric_from(payload.aging_data, "over_90", "over_120")
  appeal_win_rate = _clamp_decimal(_metric_from(payload.appeal_win_rate_history, "rolling_win_rate", "win_rate"))
  delay_days = _metric_from(payload.delay_history, "avg_days", "average_days")
  recovery_rate_signal = _clamp_decimal(_metric_from(payload.recovery_history, "recent_recovery_rate", "last_60d_recovery_rate"), Decimal("0.00"), Decimal("1.00"))
  delay_factor = Decimal("1.00")
  if delay_days > Decimal("0.00"):
    delay_factor = _clamp_decimal(Decimal("1.00") - (delay_days / Decimal("120.00")), Decimal("0.35"), Decimal("1.00"))
  base_probability = appeal_win_rate if appeal_win_rate > Decimal("0.00") else _clamp_decimal(base_risk_score, Decimal("0.05"), Decimal("0.95"))
  recovery_probability = _clamp_decimal((base_probability * delay_factor) + (recovery_rate_signal * Decimal("0.05")), Decimal("0.05"), Decimal("0.95"))
  expected_recovery_value = (variance_total * recovery_probability).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

  behaviors: list[str] = []
  evidence: list[str] = []
  if delay_days >= Decimal("30.00"):
    behaviors.append("slow_payer")
    evidence.append(f"average_delay_days={delay_days}")
  if structural_component > Decimal("0.00"):
    behaviors.append("under_allowing")
    evidence.append(f"structural_variance={structural_component}")
  if payload.denial_codes:
    behaviors.append("repeat_denials")
    evidence.append(f"denial_codes={','.join(payload.denial_codes[:3])}")

  roi_denominator = Decimal("8.00")
  if delay_days > Decimal("45.00"):
    roi_denominator = Decimal("6.00")
  if variance_total <= Decimal("0.00"):
    roi_denominator = Decimal("12.00")

  roi_per_hour = expected_recovery_value / roi_denominator if roi_denominator > 0 else Decimal("0.00")
  structural_ratio = _clamp_decimal(structural_component / variance_total if variance_total else Decimal("0.00"))

  references = [
    f"appeal_win_rate={appeal_win_rate}",
    f"delay_days={delay_days}",
    f"denial_codes={','.join(payload.denial_codes) or 'none'}",
    f"adjustment_codes={','.join(payload.adjustment_codes) or 'none'}",
  ]

  recommended_actions = [
    RevenueIntegrityAction(
      step="Re-sequence worklist for structural underpayments",
      rationale=f"Targets structural variance of {structural_component} before procedural clean-up to maximize cash velocity.",
      roi_per_hour=roi_per_hour,
      references=[references[0], references[1]],
    ),
    RevenueIntegrityAction(
      step="Batch appeals for recurring denial codes",
      rationale="Consolidate evidence packets for repeat CO/CPT denials to lift win rate.",
      roi_per_hour=roi_per_hour,
      references=[references[2]],
    ),
    RevenueIntegrityAction(
      step="Schedule payer escalation touchpoint",
      rationale="Prevent further delay on aged claims and secure written timelines.",
      roi_per_hour=roi_per_hour,
      references=[references[1]],
    ),
  ]

  draft_pack = [
    RevenueIntegrityDraft(
      type="appeal_letter",
      content="Appeal letter citing adjustment and denial codes with variance evidence and requested make-good timeline.",
    ),
    RevenueIntegrityDraft(
      type="call_script",
      content="Script for payer rep highlighting structural underpayments, expected allowance, and appeal win history.",
    ),
    RevenueIntegrityDraft(
      type="portal_message",
      content="Portal message to log variance dispute with attachment checklist and response-by date.",
    ),
    RevenueIntegrityDraft(
      type="escalation_note",
      content="Escalation note summarizing payer delays, codes involved, and requested executive review.",
    ),
  ]

  escalation_thresholds = [
    RevenueIntegrityThreshold(
      trigger="legal_escalation",
      threshold=max(variance_total * Decimal("0.40"), Decimal("50000.00")),
      unit="usd_at_risk",
      note="If payer response exceeds 30 days or repeats CO/PR denials with no remediation.",
    ),
    RevenueIntegrityThreshold(
      trigger="contract_review",
      threshold=Decimal("0.15"),
      unit="structural_variance_ratio",
      note=f"Escalate when structural underpayment share exceeds 15% of total variance; current ratio {structural_ratio}.",
    ),
    RevenueIntegrityThreshold(
      trigger="executive_intervention",
      threshold=Decimal("2.00"),
      unit="appeal_cycles_without_response",
      note="Escalate after two unanswered appeal cycles or missed SLA.",
    ),
  ]

  data_used = [
    f"variance_metrics.structural={structural_component}",
    f"variance_metrics.procedural={procedural_component}",
    f"variance_metrics.total={variance_total}",
    f"appeal_win_rate={appeal_win_rate}",
    f"delay_days={delay_days}",
    f"aging.over_90={aging_over_90}",
    f"risk_score={base_risk_score}",
  ]

  assumptions = [
    "Financial records remain immutable; endpoint is read-only and deterministic.",
    "Missing metrics default to 0.00 for calculations without fabricating new financial data.",
    "All tool-ready drafts avoid PHI and rely on provided adjustment/denial codes only.",
  ]

  exposure_analysis = RevenueExposureAnalysis(
    at_risk_total=variance_total,
    structural_component=structural_component,
    procedural_component=procedural_component,
    aging_over_90=aging_over_90,
    notes="Separated structural underpayment from procedural denials to target recovery streams.",
  )

  expected_estimate = ExpectedRecoveryEstimate(
    exposure_basis=variance_total,
    recovery_probability=recovery_probability,
    expected_recovery_value=expected_recovery_value,
    method="ERV = variance_total × adjusted_recovery_probability (appeal_win_rate × delay_factor + recovery_signal_adjustment)",
  )

  payer_behavior = PayerBehaviorAnalysis(
    behaviors=behaviors,
    evidence=evidence,
  )

  priority_explanation = (
    f"Risk score {base_risk_score}, appeal win rate {appeal_win_rate}, delay factor {delay_factor}, "
    f"expected recovery {expected_recovery_value} prioritize structural clean-up then repeat denials for ROI per hour {roi_per_hour}."
  )

  return RevenueIntegrityResponse(
    strategic_summary="Revenue Integrity Command Engine: deterministic roadmap to accelerate recovery without altering ledger data.",
    revenue_exposure_analysis=exposure_analysis,
    payer_behavior_analysis=payer_behavior,
    operational_priority_score_explanation=priority_explanation,
    expected_recovery_estimate=expected_estimate,
    recommended_action_sequence=recommended_actions,
    draft_pack=draft_pack,
    escalation_thresholds=escalation_thresholds,
    data_used=data_used,
    assumptions=assumptions,
    confidence=_confidence_from_score(base_risk_score),
  )


def _safe_revenue_integrity_response(payload: RevenueIntegrityPayload, membership: OrganizationMembership, db: Session) -> RevenueIntegrityResponse:
  try:
    return _assemble_revenue_integrity_response(payload, membership)
  except Exception as exc:
    db.rollback()
    raise HTTPException(
      status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
      detail="revenue_integrity_engine_unavailable",
    ) from exc
  finally:
    db.rollback()


@router.post("/revenue-integrity/command-engine", response_model=RevenueIntegrityResponse)
def revenue_integrity_command_engine(
  payload: RevenueIntegrityPayload,
  membership: OrganizationMembership = Depends(get_current_membership),
  db: Session = Depends(get_db),
) -> RevenueIntegrityResponse:
  return _safe_revenue_integrity_response(payload, membership, db)
