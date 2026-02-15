from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import DateTime, Date, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class RptKpiDaily(Base):
    __tablename__ = "rpt_kpi_daily"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    kpi_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    metric_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    value_num: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    value_json: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    facility_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    program_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    provider_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    payer_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
