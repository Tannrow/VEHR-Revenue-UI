from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.base import Base


class EpisodeOfCare(Base):
    __tablename__ = "episodes_of_care"

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
    admit_date: Mapped[date] = mapped_column(Date, nullable=False)
    discharge_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    referral_source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reason_for_admission: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_service_category: Mapped[str] = mapped_column(String(20), nullable=False)
    court_involved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    discharge_disposition: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="episodes_of_care",
    )
    patient: Mapped["Patient"] = relationship(
        "Patient",
        back_populates="episodes_of_care",
    )
    care_team_assignments: Mapped[list["PatientCareTeam"]] = relationship(
        "PatientCareTeam",
        back_populates="episode",
    )
    requirements: Mapped[list["PatientRequirement"]] = relationship(
        "PatientRequirement",
        back_populates="episode",
    )
    treatment_stage: Mapped["PatientTreatmentStage | None"] = relationship(
        "PatientTreatmentStage",
        back_populates="episode",
        uselist=False,
    )
    treatment_stage_events: Mapped[list["PatientTreatmentStageEvent"]] = relationship(
        "PatientTreatmentStageEvent",
        back_populates="episode",
    )
