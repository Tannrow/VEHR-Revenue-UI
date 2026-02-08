from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.core.time import utc_now


class FormTemplate(Base):
    __tablename__ = "form_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    schema_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="form_templates",
    )
    submissions: Mapped[list["FormSubmission"]] = relationship(
        "FormSubmission",
        back_populates="form_template",
    )
    service_document_templates: Mapped[list["ServiceDocumentTemplate"]] = relationship(
        "ServiceDocumentTemplate",
        back_populates="template",
    )
    patient_documents: Mapped[list["PatientDocument"]] = relationship(
        "PatientDocument",
        back_populates="template",
    )

