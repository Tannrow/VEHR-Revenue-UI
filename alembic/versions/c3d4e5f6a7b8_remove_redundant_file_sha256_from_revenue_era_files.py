"""remove redundant file_sha256 from revenue era files

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-02-21 04:05:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "c3d4e5f6a7b8"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE revenue_era_files SET sha256 = file_sha256 WHERE sha256 IS NULL AND file_sha256 IS NOT NULL"))
    op.alter_column("revenue_era_files", "sha256", existing_type=sa.String(length=64), nullable=False)
    op.drop_constraint("uq_revenue_era_files_org_file_sha256", "revenue_era_files", type_="unique")
    op.drop_column("revenue_era_files", "file_sha256")


def downgrade() -> None:
    op.add_column("revenue_era_files", sa.Column("file_sha256", sa.String(length=64), nullable=True))
    op.execute(sa.text("UPDATE revenue_era_files SET file_sha256 = sha256 WHERE file_sha256 IS NULL"))
    op.alter_column("revenue_era_files", "file_sha256", existing_type=sa.String(length=64), nullable=False)
    op.create_unique_constraint(
        "uq_revenue_era_files_org_file_sha256",
        "revenue_era_files",
        ["organization_id", "file_sha256"],
    )
