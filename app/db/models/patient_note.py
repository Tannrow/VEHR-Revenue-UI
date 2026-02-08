from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.base import Base


class PatientNote(Base):
    __tablename__ = "patient_notes"

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
    primary_service_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("services.id"),
        nullable=False,
        index=True,
    )
    visibility: Mapped[str] = mapped_column(String(30), nullable=False, default="clinical_only")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="patient_notes",
    )
    patient: Mapped["Patient"] = relationship(
        "Patient",
        back_populates="notes",
    )
    primary_service: Mapped["Service"] = relationship(
        "Service",
        back_populates="primary_notes",
    )
    created_by_user: Mapped["User | None"] = relationship(
        "User",
        back_populates="patient_notes",
    )
