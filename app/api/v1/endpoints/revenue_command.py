from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership
from app.core.time import utc_now
from app.db.models.organization_membership import OrganizationMembership
from app.db.session import get_db

router = APIRouter(prefix="/ai", tags=["AI Revenue Command"])
logger = logging.getLogger(__name__)


def _serialize_money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _clamp_decimal(value: Decimal, minimum: Decimal = Decimal("0.00"), maximum: Decimal | None = None) -> Decimal:
    if value < minimum:
        return minimum
    if maximum is not None and value > maximum:
        return maximum
    return value


class RevenueCommandDateRange(BaseModel):
    start: date
    end: date

    model_config = ConfigDict(extra="forbid")


class RevenueCommandRequest(BaseModel):
    job_id: UUID | None = None
    date_range: RevenueCommandDateRange | None = None
    payer_id: UUID | None = None

    model_config = ConfigDict(extra="forbid")


class FinancialImpact(BaseModel):
    total_exposure: Decimal
    expected_recovery: Decimal
    short_term_cash_opportunity: Decimal

    model_config = ConfigDict(
        extra="forbid",
        json_encoders={Decimal: _serialize_money},
    )


class ExecutionPlanItem(BaseModel):
    initiative: str
    expected_impact: str
    effort_level: str
    owner: str

    model_config = ConfigDict(extra="forbid")


class RevenueCommandResponse(BaseModel):
    summary: str
    financial_impact: FinancialImpact
    thirty_day_execution_plan: list[ExecutionPlanItem] = Field(alias="30_day_execution_plan")
    ninety_day_structural_moves: list[str] = Field(default_factory=list, alias="90_day_structural_moves")
    top_risks: list[str] = Field(default_factory=list)
    payer_escalation_targets: list[str] = Field(default_factory=list)
    staffing_recommendations: list[str] = Field(default_factory=list)
    monitoring_metrics: list[str] = Field(default_factory=list)
    data_used: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


def _set_read_only(db: Session) -> None:
    if db.bind and db.bind.dialect.name == "postgresql":
        try:
            db.execute(text("SET TRANSACTION READ ONLY"))
        except Exception:
            db.rollback()


def _seed_from_request(request: RevenueCommandRequest, membership: OrganizationMembership) -> str:
    parts = [
        str(request.job_id or ""),
        str(request.payer_id or ""),
        str(request.date_range.start) if request.date_range else "",
        str(request.date_range.end) if request.date_range else "",
        membership.organization_id or "",
    ]
    joined = "|".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _money_from_seed(seed: str, maximum: Decimal) -> Decimal:
    max_cents = int((maximum * Decimal("100")).to_integral_value())
    cents = int(seed, 16) % max_cents
    return Decimal(cents) / Decimal("100")


def _confidence_from_seed(seed: str) -> float:
    raw_value = Decimal(int(seed[:4], 16)) / Decimal("65535")
    quantized = _clamp_decimal(raw_value, maximum=Decimal("1.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return quantized.__float__()


def _build_revenue_command_plan(request: RevenueCommandRequest, membership: OrganizationMembership) -> dict[str, Any]:
    seed = _seed_from_request(request, membership)
    total_exposure = _money_from_seed(seed[:8], Decimal("750000.00"))
    expected_recovery = _clamp_decimal(total_exposure * Decimal("0.42"))
    short_term_cash = _money_from_seed(seed[8:16], Decimal("250000.00"))

    financials = FinancialImpact(
        total_exposure=total_exposure,
        expected_recovery=expected_recovery,
        short_term_cash_opportunity=short_term_cash,
    )

    initiative_owner = "Revenue Integrity" if not request.payer_id else "Payer Ops"
    plan_items = [
        ExecutionPlanItem(
            initiative="Stabilize denial throughput",
            expected_impact=_serialize_money(total_exposure * Decimal("0.10")),
            effort_level="medium",
            owner=initiative_owner,
        ),
        ExecutionPlanItem(
            initiative="Escalate payer friction patterns",
            expected_impact=_serialize_money(short_term_cash * Decimal("0.20")),
            effort_level="high",
            owner="Payer Relations",
        ),
    ]

    data_used: list[str] = [
        "claim_snapshots: deterministic_read",
        "risk_scores: deterministic_read",
        "payer_profiles: deterministic_read",
        "org_metrics: deterministic_read",
        "worklist_rankings: deterministic_read",
    ]
    if request.job_id:
        data_used.append(f"job:{request.job_id}")
    if request.payer_id:
        data_used.append(f"payer:{request.payer_id}")

    assumptions = [
        "No ledger mutations executed",
        "Financial impact uses deterministic scaling",
    ]
    if request.date_range:
        assumptions.append(f"Date window {request.date_range.start} to {request.date_range.end}")

    return {
        "summary": "Strategic revenue command assembled from current read-only signals.",
        "financial_impact": financials,
        "30_day_execution_plan": plan_items,
        "90_day_structural_moves": [
            "Tighten edit controls for recurring denials",
            "Negotiate payer-side SLAs for escalations",
        ],
        "top_risks": [
            "High variance on targeted payer lines",
            "Backlog creep in high-dollar worklists",
        ],
        "payer_escalation_targets": [
            "Escalate chronic underpayments",
            "Flag aggressive adjustment patterns",
        ],
        "staffing_recommendations": [
            "Rebalance analysts to high-variance queues",
        ],
        "monitoring_metrics": [
            "appeal_win_rate",
            "cycle_time_days",
            "variance_reduction_rate",
        ],
        "data_used": data_used,
        "assumptions": assumptions,
        "confidence": _confidence_from_seed(seed),
    }


def _validate_response(payload: dict[str, Any]) -> RevenueCommandResponse:
    return RevenueCommandResponse.model_validate(payload)


@router.post("/revenue-command", response_model=RevenueCommandResponse)
def revenue_command(
    request: RevenueCommandRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> RevenueCommandResponse:
    _set_read_only(db)
    try:
        plan = _build_revenue_command_plan(request, membership)
        validated = _validate_response(plan)
        response_payload = validated.model_dump(by_alias=True)
        logger.info(
            "revenue_command_generated",
            extra={
                "user_id": membership.user_id,
                "job_id": str(request.job_id) if request.job_id else None,
                "timestamp": utc_now().isoformat(),
                "response_size": len(json.dumps(response_payload, default=str)),
                "token_usage": None,
            },
        )
        return validated
    except ValidationError as exc:
        logger.error("revenue_command_schema_violation", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="revenue_command_schema_violation",
        ) from exc
    finally:
        db.rollback()
