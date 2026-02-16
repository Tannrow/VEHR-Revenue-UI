from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class ReconLineResult(Base):
    __tablename__ = "recon_line_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("recon_import_jobs.id"), nullable=False, index=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)

    account_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    dos_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    dos_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    proc_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    billed_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    paid_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    variance_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    match_status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    reason_code: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
