from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Date, DateTime, Enum as PgEnum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class ClaimLedgerStatus(str, Enum):
    NOT_BILLED = "NOT_BILLED"
    BILLED_NO_RESPONSE = "BILLED_NO_RESPONSE"
    PAID_IN_FULL = "PAID_IN_FULL"
    PARTIAL_PAYMENT = "PARTIAL_PAYMENT"
    DENIED = "DENIED"
    OVERPAID = "OVERPAID"


class ClaimLedger(Base):
    __tablename__ = "claim_ledgers"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    claim_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("claims.id"), nullable=False, unique=True, index=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)

    total_billed: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    total_paid: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    total_allowed: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    total_adjusted: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    variance: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    status: Mapped[ClaimLedgerStatus] = mapped_column(PgEnum(ClaimLedgerStatus, name="claim_ledger_status"), nullable=False, index=True)
    aging_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_event_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
