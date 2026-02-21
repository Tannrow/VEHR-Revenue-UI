"""add revenue era processing stage fields

Revision ID: 9f1e2d3c4b6a
Revises: c3d4e5f6a7b8
Create Date: 2026-02-21 07:58:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "9f1e2d3c4b6a"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("revenue_era_files", sa.Column("current_stage", sa.String(length=50), nullable=True))
    op.add_column("revenue_era_files", sa.Column("stage_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("revenue_era_files", sa.Column("stage_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("revenue_era_files", sa.Column("last_error_stage", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("revenue_era_files", "last_error_stage")
    op.drop_column("revenue_era_files", "stage_completed_at")
    op.drop_column("revenue_era_files", "stage_started_at")
    op.drop_column("revenue_era_files", "current_stage")
