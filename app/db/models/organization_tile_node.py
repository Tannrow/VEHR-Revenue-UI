from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.base import Base


class OrganizationTileNode(Base):
    __tablename__ = "organization_tile_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    tile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organization_tiles.id"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("organization_tile_nodes.id"),
        nullable=True,
        index=True,
    )
    node_type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="organization_tile_nodes",
    )
    tile: Mapped["OrganizationTile"] = relationship(
        "OrganizationTile",
        back_populates="nodes",
    )
    parent: Mapped["OrganizationTileNode | None"] = relationship(
        "OrganizationTileNode",
        remote_side="OrganizationTileNode.id",
        back_populates="children",
    )
    children: Mapped[list["OrganizationTileNode"]] = relationship(
        "OrganizationTileNode",
        back_populates="parent",
    )
    created_by_user: Mapped["User | None"] = relationship(
        "User",
        back_populates="created_organization_tile_nodes",
    )
