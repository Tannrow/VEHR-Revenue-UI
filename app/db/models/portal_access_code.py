from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.base import Base


class PortalAccessCode(Base):
    __tablename__ = "portal_access_codes"

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
    patient_document_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("patient_documents.id"),
        nullable=True,
        index=True,
    )
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="portal_access_codes",
    )
    patient: Mapped["Patient"] = relationship(
        "Patient",
        back_populates="portal_access_codes",
    )
    patient_document: Mapped["PatientDocument | None"] = relationship(
        "PatientDocument",
        back_populates="portal_access_codes",
    )
