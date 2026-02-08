from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.base import Base


class PatientDocument(Base):
    __tablename__ = "patient_documents"
    __table_args__ = (
        UniqueConstraint(
            "enrollment_id",
            "template_id",
            name="uq_patient_documents_enrollment_template",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    patient_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
    )
    service_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("services.id"),
        nullable=False,
        index=True,
    )
    enrollment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("patient_service_enrollments.id"),
        nullable=False,
        index=True,
    )
    template_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("form_templates.id"),
        nullable=False,
        index=True,
    )
    service_document_template_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("service_document_templates.id"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="patient_documents",
    )
    patient: Mapped["Patient"] = relationship(
        "Patient",
        back_populates="patient_documents",
    )
    service: Mapped["Service"] = relationship(
        "Service",
        back_populates="patient_documents",
    )
    enrollment: Mapped["PatientServiceEnrollment"] = relationship(
        "PatientServiceEnrollment",
        back_populates="patient_documents",
    )
    template: Mapped["FormTemplate"] = relationship(
        "FormTemplate",
        back_populates="patient_documents",
    )
    service_document_template: Mapped["ServiceDocumentTemplate | None"] = relationship(
        "ServiceDocumentTemplate",
        back_populates="patient_documents",
    )
    portal_access_codes: Mapped[list["PortalAccessCode"]] = relationship(
        "PortalAccessCode",
        back_populates="patient_document",
    )
