from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from sqlalchemy import Date, DateTime, Enum as PgEnum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class ClaimEventType(str, Enum):
    SERVICE_RECORDED = "SERVICE_RECORDED"
    ERA_RECEIVED = "ERA_RECEIVED"
    PAYMENT = "PAYMENT"
    DENIAL = "DENIAL"
    ADJUSTMENT = "ADJUSTMENT"


class ClaimEvent(Base):
    __tablename__ = "claim_events"
    __table_args__ = (
        UniqueConstraint("claim_id", "event_type", "job_id", name="uq_claim_event_per_job"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    claim_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("claims.id"), nullable=False, index=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)

    event_type: Mapped[ClaimEventType] = mapped_column(PgEnum(ClaimEventType, name="claim_event_type"), nullable=False)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("recon_import_jobs.id"), nullable=True)
    raw_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
