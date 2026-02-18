from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class ClaimLine(Base):
    __tablename__ = "claim_lines"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    claim_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("claims.id"), nullable=False, index=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)

    cpt_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    units: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    expected_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
