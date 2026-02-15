from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class AnalyticsAlert(Base):
    __tablename__ = "analytics_alerts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)

    alert_type: Mapped[str] = mapped_column(String(40), nullable=False, default="anomaly")
    metric_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    report_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    baseline_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    comparison_period: Mapped[str] = mapped_column(String(80), nullable=False)

    current_range_start: Mapped[date] = mapped_column(Date, nullable=False)
    current_range_end: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_range_start: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_range_end: Mapped[date] = mapped_column(Date, nullable=False)

    current_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    baseline_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    delta_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    delta_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    recommended_actions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    context_filters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)

    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

