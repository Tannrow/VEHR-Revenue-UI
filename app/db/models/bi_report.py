from __future__ import annotations

import os
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base

DEFAULT_BI_RLS_ROLE = "TenantRLS"
DEFAULT_WORKSPACE_ID_FALLBACK = "b64502e3-dc61-413b-9666-96e106133208"


def _default_workspace_id() -> str:
    return (
        os.getenv("PBI_DEFAULT_WORKSPACE_ID", "").strip()
        or DEFAULT_WORKSPACE_ID_FALLBACK
    )


def _default_rls_role() -> str:
    return (
        os.getenv("PBI_RLS_ROLE", DEFAULT_BI_RLS_ROLE).strip()
        or DEFAULT_BI_RLS_ROLE
    )


class BIReport(Base):
    __tablename__ = "bi_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    report_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False, default=_default_workspace_id)
    report_id: Mapped[str] = mapped_column(String(36), nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    rls_role: Mapped[str] = mapped_column(String(120), nullable=False, default=_default_rls_role)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
