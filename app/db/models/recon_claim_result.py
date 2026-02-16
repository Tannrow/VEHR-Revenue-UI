from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class ReconClaimResult(Base):
    __tablename__ = "recon_claim_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("recon_import_jobs.id"), nullable=False, index=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)

    account_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    billed_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    paid_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    variance_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    line_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
