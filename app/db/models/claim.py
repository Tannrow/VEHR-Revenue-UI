from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, String, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)

    external_claim_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    patient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    member_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payer_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    dos_from: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    dos_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    resubmission_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
