from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership
from app.core.time import utc_now
from app.db.session import get_db
from app.db.models.organization_membership import OrganizationMembership


router = APIRouter(prefix="/ai", tags=["AI Finance"])

CONTEXT_PACK_VERSION = "2024.12.0"


class FinanceRecommendedAction(BaseModel):
  action: str
  impact_estimate: Decimal
  urgency: Literal["high", "medium", "low"]

  model_config = ConfigDict(json_encoders={Decimal: lambda value: str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))})


class FinanceDraft(BaseModel):
  type: str
  content: str


class FinanceAIResponse(BaseModel):
  summary: str
  root_cause: str
  recommended_actions: list[FinanceRecommendedAction] = Field(default_factory=list)
  drafts: list[FinanceDraft] = Field(default_factory=list)
  questions_needed: list[str] = Field(default_factory=list)
  assumptions: list[str] = Field(default_factory=list)
  data_used: dict[str, Any] | list[Any] | None = Field(default_factory=dict)
  confidence: Literal["low", "medium", "high"]


class FinanceAIEnvelope(BaseModel):
  context_pack_version: str
  generated_at: datetime
  risk_score: Decimal
  advisory: FinanceAIResponse

  model_config = ConfigDict(json_encoders={Decimal: lambda value: str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))})


class FinanceAIContext(BaseModel):
  scope: str | None = None
  claim_ids: list[str] = Field(default_factory=list)
  payer: str | None = None
  cohort: str | None = None
  period: str | None = None
  narrative: str | None = None
  include_drafts: bool = True


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


def _assemble_response(kind: str, context: FinanceAIContext, membership: OrganizationMembership) -> FinanceAIEnvelope:
  seed = f"{membership.organization_id}:{membership.user_id}:{kind}:{context.scope or ''}:{','.join(context.claim_ids)}:{context.payer or ''}"
  risk_score = _deterministic_score(seed)
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
    ],
    data_used={
      "context_scope": context.scope,
      "claim_ids": context.claim_ids,
      "payer": context.payer,
      "cohort": context.cohort,
      "period": context.period,
    },
    confidence=confidence,
  )

  return FinanceAIEnvelope(
    context_pack_version=CONTEXT_PACK_VERSION,
    generated_at=utc_now(),
    risk_score=risk_score,
    advisory=response,
  )


def _safe_response(kind: str, context: FinanceAIContext, membership: OrganizationMembership, db: Session) -> FinanceAIEnvelope:
  try:
    return _assemble_response(kind, context, membership)
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
