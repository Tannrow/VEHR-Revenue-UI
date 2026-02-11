from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.base import Base


class OrganizationRolePermission(Base):
    __tablename__ = "organization_role_permissions"
    __table_args__ = (
        UniqueConstraint(
            "organization_role_id",
            "permission",
            name="uq_organization_role_permissions_role_permission",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_role_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organization_roles.id"),
        nullable=False,
        index=True,
    )
    permission: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    role: Mapped["OrganizationRole"] = relationship(
        "OrganizationRole",
        back_populates="permissions",
    )
