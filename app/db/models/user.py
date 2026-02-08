from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.core.time import utc_now


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        "OrganizationMembership",
        back_populates="user",
    )
    triggered_clinical_audit_runs: Mapped[list["ClinicalAuditRun"]] = relationship(
        "ClinicalAuditRun",
        back_populates="triggered_by_user",
    )
    assigned_review_queue_items: Mapped[list["ReviewQueueItem"]] = relationship(
        "ReviewQueueItem",
        back_populates="assigned_to_user",
    )
    review_actions: Mapped[list["ReviewAction"]] = relationship(
        "ReviewAction",
        back_populates="created_by_user",
    )
    review_evidence_links: Mapped[list["ReviewEvidenceLink"]] = relationship(
        "ReviewEvidenceLink",
        back_populates="created_by_user",
    )
    assigned_service_enrollments: Mapped[list["PatientServiceEnrollment"]] = relationship(
        "PatientServiceEnrollment",
        back_populates="assigned_staff_user",
    )
    patient_notes: Mapped[list["PatientNote"]] = relationship(
        "PatientNote",
        back_populates="created_by_user",
    )
    disclosure_logs: Mapped[list["DisclosureLog"]] = relationship(
        "DisclosureLog",
        back_populates="generated_by_user",
    )

