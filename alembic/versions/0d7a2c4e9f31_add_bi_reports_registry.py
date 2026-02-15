"""add bi reports registry table

Revision ID: 0d7a2c4e9f31
Revises: c9f4d2e7a1b3
Create Date: 2026-02-15 00:00:00.000000
"""

import os

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0d7a2c4e9f31"
down_revision = "c9f4d2e7a1b3"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = (
    os.getenv("PBI_DEFAULT_WORKSPACE_ID", "").strip()
    or "b64502e3-dc61-413b-9666-96e106133208"
)
DEFAULT_RLS_ROLE = os.getenv("PBI_RLS_ROLE", "TenantRLS").strip() or "TenantRLS"


def _quoted(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def upgrade() -> None:
    op.create_table(
        "bi_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("report_key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            nullable=False,
            server_default=sa.text(_quoted(DEFAULT_WORKSPACE_ID)),
        ),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column(
            "rls_role",
            sa.String(length=120),
            nullable=False,
            server_default=sa.text(_quoted(DEFAULT_RLS_ROLE)),
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bi_reports_report_key", "bi_reports", ["report_key"], unique=True)
    op.create_index("ix_bi_reports_is_enabled", "bi_reports", ["is_enabled"])


def downgrade() -> None:
    op.drop_index("ix_bi_reports_is_enabled", table_name="bi_reports")
    op.drop_index("ix_bi_reports_report_key", table_name="bi_reports")
    op.drop_table("bi_reports")
