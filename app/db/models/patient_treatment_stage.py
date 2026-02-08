from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.base import Base


class PatientTreatmentStage(Base):
    __tablename__ = "patient_treatment_stage"

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
    episode_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("episodes_of_care.id"),
        nullable=False,
        index=True,
        unique=True,
    )
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="patient_treatment_stages",
    )
    patient: Mapped["Patient"] = relationship(
        "Patient",
        back_populates="treatment_stages",
    )
    episode: Mapped["EpisodeOfCare"] = relationship(
        "EpisodeOfCare",
        back_populates="treatment_stage",
    )
    updated_by_user: Mapped["User | None"] = relationship(
        "User",
        back_populates="updated_treatment_stages",
    )
    events: Mapped[list["PatientTreatmentStageEvent"]] = relationship(
        "PatientTreatmentStageEvent",
        back_populates="patient_treatment_stage",
    )
