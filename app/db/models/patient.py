from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.core.time import utc_now


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=True,
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="patients",
    )
    encounters: Mapped[list["Encounter"]] = relationship(
        "Encounter",
        back_populates="patient",
    )
    form_submissions: Mapped[list["FormSubmission"]] = relationship(
        "FormSubmission",
        back_populates="patient",
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="patient",
    )
    service_enrollments: Mapped[list["PatientServiceEnrollment"]] = relationship(
        "PatientServiceEnrollment",
        back_populates="patient",
    )
    notes: Mapped[list["PatientNote"]] = relationship(
        "PatientNote",
        back_populates="patient",
    )

