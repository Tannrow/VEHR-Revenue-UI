from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.base import Base


class DisclosureLog(Base):
    __tablename__ = "disclosure_logs"

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
    generated_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    export_type: Mapped[str] = mapped_column(String(50), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    disclosed_note_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="disclosure_logs",
    )
    patient: Mapped["Patient"] = relationship(
        "Patient",
        back_populates="disclosure_logs",
    )
    service: Mapped["Service"] = relationship(
        "Service",
        back_populates="disclosure_logs",
    )
    generated_by_user: Mapped["User | None"] = relationship(
        "User",
        back_populates="disclosure_logs",
    )
