from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression
from sqlalchemy.types import JSON

from app.core.time import utc_now
from app.db.base import Base


def _json_type() -> JSON:
    """
    Allow SQLite-based unit tests to create tables while keeping JSONB for Postgres.
    """
    return JSON().with_variant(JSONB(astext_type=Text()), "postgresql")


class RevenueEraFile(Base):
    __tablename__ = "revenue_era_files"
    __table_args__ = (
        UniqueConstraint("organization_id", "sha256", name="uq_revenue_era_files_org_sha"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payer_name_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    storage_ref: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    current_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stage_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stage_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=expression.text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=expression.text("CURRENT_TIMESTAMP"),
    )

    extract_results: Mapped[list["RevenueEraExtractResult"]] = relationship(
        "RevenueEraExtractResult",
        back_populates="era_file",
        cascade="all, delete-orphan",
    )
    structured_results: Mapped[list["RevenueEraStructuredResult"]] = relationship(
        "RevenueEraStructuredResult",
        back_populates="era_file",
        cascade="all, delete-orphan",
    )
    claim_lines: Mapped[list["RevenueEraClaimLine"]] = relationship(
        "RevenueEraClaimLine",
        back_populates="era_file",
        cascade="all, delete-orphan",
    )
    work_items: Mapped[list["RevenueEraWorkItem"]] = relationship(
        "RevenueEraWorkItem",
        back_populates="era_file",
        cascade="all, delete-orphan",
    )
    processing_logs: Mapped[list["RevenueEraProcessingLog"]] = relationship(
        "RevenueEraProcessingLog",
        back_populates="era_file",
        cascade="all, delete-orphan",
    )
    validation_reports: Mapped[list["RevenueEraValidationReport"]] = relationship(
        "RevenueEraValidationReport",
        back_populates="era_file",
        cascade="all, delete-orphan",
    )


class RevenueEraExtractResult(Base):
    __tablename__ = "revenue_era_extract_results"
    __table_args__ = (
        UniqueConstraint("era_file_id", name="uq_revenue_era_extract_results_file"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    era_file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("revenue_era_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    extractor: Mapped[str] = mapped_column(String(50), nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_json: Mapped[dict] = mapped_column(_json_type(), nullable=False)
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=expression.text("CURRENT_TIMESTAMP"),
    )

    era_file: Mapped[RevenueEraFile] = relationship("RevenueEraFile", back_populates="extract_results")


class RevenueEraStructuredResult(Base):
    __tablename__ = "revenue_era_structured_results"
    __table_args__ = (
        UniqueConstraint("era_file_id", name="uq_revenue_era_structured_results_file"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    era_file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("revenue_era_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    llm: Mapped[str] = mapped_column(String(50), nullable=False)
    deployment: Mapped[str] = mapped_column(Text, nullable=False)
    api_version: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    structured_json: Mapped[dict] = mapped_column(_json_type(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=expression.text("CURRENT_TIMESTAMP"),
    )

    era_file: Mapped[RevenueEraFile] = relationship("RevenueEraFile", back_populates="structured_results")


class RevenueEraProcessingLog(Base):
    __tablename__ = "revenue_era_processing_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    era_file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("revenue_era_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=expression.text("CURRENT_TIMESTAMP"),
    )

    era_file: Mapped[RevenueEraFile] = relationship("RevenueEraFile", back_populates="processing_logs")


class RevenueEraClaimLine(Base):
    __tablename__ = "revenue_era_claim_lines"
    __table_args__ = (
        UniqueConstraint("era_file_id", "line_index", name="uq_revenue_era_claim_lines_file_idx"),
        UniqueConstraint(
            "era_file_id",
            "claim_ref",
            "service_date",
            "proc_code",
            name="uq_revenue_era_claim_lines_claim_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    era_file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("revenue_era_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_index: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_ref: Mapped[str] = mapped_column(Text, nullable=False)
    service_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    proc_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    charge_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    allowed_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    paid_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    adjustments_json: Mapped[dict | None] = mapped_column(_json_type(), nullable=True)
    match_status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=expression.text("CURRENT_TIMESTAMP"),
    )

    era_file: Mapped[RevenueEraFile] = relationship("RevenueEraFile", back_populates="claim_lines")
    work_items: Mapped[list["RevenueEraWorkItem"]] = relationship(
        "RevenueEraWorkItem",
        back_populates="claim_line",
    )


class RevenueEraWorkItem(Base):
    __tablename__ = "revenue_era_work_items"
    __table_args__ = (
        UniqueConstraint("era_file_id", "claim_ref", name="uq_revenue_era_work_items_file_claim"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    era_file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("revenue_era_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    era_claim_line_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("revenue_era_claim_lines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    dollars_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payer_name: Mapped[str] = mapped_column(Text, nullable=False)
    claim_ref: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=expression.text("CURRENT_TIMESTAMP"),
    )

    era_file: Mapped[RevenueEraFile] = relationship("RevenueEraFile", back_populates="work_items")
    claim_line: Mapped[RevenueEraClaimLine | None] = relationship("RevenueEraClaimLine", back_populates="work_items")


class RevenueEraValidationReport(Base):
    __tablename__ = "era_validation_report"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    era_file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("revenue_era_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim_count: Mapped[int] = mapped_column(Integer, nullable=False)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False)
    work_item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_paid_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_adjustment_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_patient_resp_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    net_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reconciled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    declared_total_missing: Mapped[bool] = mapped_column(Boolean, nullable=False)
    phi_scan_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    phi_hit_count: Mapped[int] = mapped_column(Integer, nullable=False)
    finalized: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=expression.text("CURRENT_TIMESTAMP"),
    )

    era_file: Mapped[RevenueEraFile] = relationship("RevenueEraFile", back_populates="validation_reports")


Index(
    "ix_revenue_era_work_items_dollars_cents_desc",
    RevenueEraWorkItem.dollars_cents.desc(),
)
