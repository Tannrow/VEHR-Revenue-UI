from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class RevenueCommandSnapshot(Base):
    __tablename__ = "revenue_command_snapshot"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )

    total_exposure: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    expected_recovery_30_day: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    short_term_cash_opportunity: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    high_risk_claim_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    critical_pre_submission_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    top_aggressive_payers: Mapped[dict | list] = mapped_column(JSONB, nullable=False, default=list)
    top_revenue_loss_drivers: Mapped[dict | list] = mapped_column(JSONB, nullable=False, default=list)
    worklist_priority_summary: Mapped[dict | list] = mapped_column(JSONB, nullable=False, default=dict)
    execution_plan_30_day: Mapped[dict | list] = mapped_column(JSONB, nullable=False, default=list)
    structural_moves_90_day: Mapped[dict | list] = mapped_column(JSONB, nullable=False, default=list)
    aggression_change_alerts: Mapped[dict | list] = mapped_column(JSONB, nullable=False, default=list)

    risk_scoring_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0")
    aggression_scoring_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0")
    pre_submission_scoring_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0")
