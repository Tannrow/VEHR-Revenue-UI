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
    sent_invites: Mapped[list["Invite"]] = relationship(
        "Invite",
        back_populates="invited_by_user",
    )
    password_reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(
        "PasswordResetToken",
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
    patient_care_team_assignments: Mapped[list["PatientCareTeam"]] = relationship(
        "PatientCareTeam",
        back_populates="user",
    )
    updated_treatment_stages: Mapped[list["PatientTreatmentStage"]] = relationship(
        "PatientTreatmentStage",
        back_populates="updated_by_user",
    )
    patient_treatment_stage_events: Mapped[list["PatientTreatmentStageEvent"]] = relationship(
        "PatientTreatmentStageEvent",
        back_populates="changed_by_user",
    )
    patient_notes: Mapped[list["PatientNote"]] = relationship(
        "PatientNote",
        back_populates="created_by_user",
        foreign_keys="PatientNote.created_by_user_id",
    )
    signed_patient_notes: Mapped[list["PatientNote"]] = relationship(
        "PatientNote",
        back_populates="signed_by_user",
        foreign_keys="PatientNote.signed_by_user_id",
    )
    disclosure_logs: Mapped[list["DisclosureLog"]] = relationship(
        "DisclosureLog",
        back_populates="generated_by_user",
    )
    created_organization_tiles: Mapped[list["OrganizationTile"]] = relationship(
        "OrganizationTile",
        back_populates="created_by_user",
    )
    created_announcements: Mapped[list["Announcement"]] = relationship(
        "Announcement",
        back_populates="created_by_user",
    )
    created_organization_tile_nodes: Mapped[list["OrganizationTileNode"]] = relationship(
        "OrganizationTileNode",
        back_populates="created_by_user",
    )

