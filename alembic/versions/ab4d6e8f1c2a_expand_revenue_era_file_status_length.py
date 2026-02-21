"""expand revenue era file status length

Revision ID: ab4d6e8f1c2a
Revises: 9f1e2d3c4b6a
Create Date: 2026-02-21 08:28:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "ab4d6e8f1c2a"
down_revision = "9f1e2d3c4b6a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "revenue_era_files",
        "status",
        existing_type=sa.String(length=20),
        type_=sa.String(length=50),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "revenue_era_files",
        "status",
        existing_type=sa.String(length=50),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
