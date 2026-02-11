from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.base import Base


class ReceptionCallWorkflow(Base):
    __tablename__ = "reception_call_workflows"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "ringcentral_event_id",
            name="uq_reception_workflow_org_event",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    ringcentral_event_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ringcentral_events.id"),
        nullable=False,
        index=True,
    )
    workflow_status: Mapped[str] = mapped_column(String(64), nullable=False, default="missed")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    handled_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    followup_task_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("tasks.id"),
        nullable=True,
        index=True,
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
        back_populates="reception_call_workflows",
    )
    ringcentral_event: Mapped["RingCentralEvent"] = relationship(
        "RingCentralEvent",
        back_populates="workflows",
    )
    handled_by_user: Mapped["User | None"] = relationship("User")
    followup_task: Mapped["Task | None"] = relationship("Task")
