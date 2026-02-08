from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.core.time import utc_now


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    patients: Mapped[list["Patient"]] = relationship(
        "Patient",
        back_populates="organization",
    )
    encounters: Mapped[list["Encounter"]] = relationship(
        "Encounter",
        back_populates="organization",
    )
    form_templates: Mapped[list["FormTemplate"]] = relationship(
        "FormTemplate",
        back_populates="organization",
    )
    form_submissions: Mapped[list["FormSubmission"]] = relationship(
        "FormSubmission",
        back_populates="organization",
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="organization",
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        "AuditEvent",
        back_populates="organization",
    )
    outbox_events: Mapped[list["EventOutbox"]] = relationship(
        "EventOutbox",
        back_populates="organization",
    )
    webhooks: Mapped[list["WebhookEndpoint"]] = relationship(
        "WebhookEndpoint",
        back_populates="organization",
    )
    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        "OrganizationMembership",
        back_populates="organization",
    )
    clinical_audit_runs: Mapped[list["ClinicalAuditRun"]] = relationship(
        "ClinicalAuditRun",
        back_populates="organization",
    )
    clinical_audit_findings: Mapped[list["ClinicalAuditFinding"]] = relationship(
        "ClinicalAuditFinding",
        back_populates="organization",
    )
    review_queue_items: Mapped[list["ReviewQueueItem"]] = relationship(
        "ReviewQueueItem",
        back_populates="organization",
    )
    review_actions: Mapped[list["ReviewAction"]] = relationship(
        "ReviewAction",
        back_populates="organization",
    )
    review_evidence_links: Mapped[list["ReviewEvidenceLink"]] = relationship(
        "ReviewEvidenceLink",
        back_populates="organization",
    )
    services: Mapped[list["Service"]] = relationship(
        "Service",
        back_populates="organization",
    )
    patient_service_enrollments: Mapped[list["PatientServiceEnrollment"]] = relationship(
        "PatientServiceEnrollment",
        back_populates="organization",
    )
    patient_notes: Mapped[list["PatientNote"]] = relationship(
        "PatientNote",
        back_populates="organization",
    )
    service_document_templates: Mapped[list["ServiceDocumentTemplate"]] = relationship(
        "ServiceDocumentTemplate",
        back_populates="organization",
    )
    patient_documents: Mapped[list["PatientDocument"]] = relationship(
        "PatientDocument",
        back_populates="organization",
    )
    portal_access_codes: Mapped[list["PortalAccessCode"]] = relationship(
        "PortalAccessCode",
        back_populates="organization",
    )
    disclosure_logs: Mapped[list["DisclosureLog"]] = relationship(
        "DisclosureLog",
        back_populates="organization",
    )
    organization_tiles: Mapped[list["OrganizationTile"]] = relationship(
        "OrganizationTile",
        back_populates="organization",
    )
    announcements: Mapped[list["Announcement"]] = relationship(
        "Announcement",
        back_populates="organization",
    )
    organization_tile_nodes: Mapped[list["OrganizationTileNode"]] = relationship(
        "OrganizationTileNode",
        back_populates="organization",
    )

