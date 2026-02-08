from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.base import Base


class ServiceDocumentTemplate(Base):
    __tablename__ = "service_document_templates"
    __table_args__ = (
        UniqueConstraint(
            "service_id",
            "template_id",
            "trigger",
            name="uq_service_document_templates_service_template_trigger",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    service_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("services.id"),
        nullable=False,
        index=True,
    )
    template_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("form_templates.id"),
        nullable=False,
        index=True,
    )
    requirement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    validity_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="service_document_templates",
    )
    service: Mapped["Service"] = relationship(
        "Service",
        back_populates="document_templates",
    )
    template: Mapped["FormTemplate"] = relationship(
        "FormTemplate",
        back_populates="service_document_templates",
    )
    patient_documents: Mapped[list["PatientDocument"]] = relationship(
        "PatientDocument",
        back_populates="service_document_template",
    )
