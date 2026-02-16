from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class ReconImportJob(Base):
    __tablename__ = "recon_import_jobs"
    __table_args__ = (
        UniqueConstraint("org_id", "era_sha256", name="uq_recon_import_jobs_org_era_sha256"),
        UniqueConstraint("org_id", "billed_sha256", name="uq_recon_import_jobs_org_billed_sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    uploaded_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)

    era_original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    era_storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    era_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    billed_original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    billed_storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    billed_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    pages_detected_era: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tables_detected_era: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claims_extracted_era: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lines_extracted_era: Mapped[int | None] = mapped_column(Integer, nullable=True)

    pages_detected_billed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lines_extracted_billed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    skipped_counts_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    matched_claims: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unmatched_era_claims: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unmatched_billed_claims: Mapped[int | None] = mapped_column(Integer, nullable=True)
    underpaid_claims: Mapped[int | None] = mapped_column(Integer, nullable=True)
    denied_claims: Mapped[int | None] = mapped_column(Integer, nullable=True)
    needs_review_claims: Mapped[int | None] = mapped_column(Integer, nullable=True)

    output_xlsx_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
