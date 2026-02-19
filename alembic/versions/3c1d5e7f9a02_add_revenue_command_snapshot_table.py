"""add revenue command snapshot table

Revision ID: 3c1d5e7f9a02
Revises: 2c4d6e8f1234
Create Date: 2026-02-19 14:41:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "3c1d5e7f9a02"
down_revision = "2c4d6e8f1234"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    json_type = postgresql.JSONB(astext_type=sa.Text()) if dialect == "postgresql" else sa.JSON()
    json_obj_default = sa.text("'{}'::jsonb") if dialect == "postgresql" else sa.text("'{}'")
    json_array_default = sa.text("'[]'::jsonb") if dialect == "postgresql" else sa.text("'[]'")

    op.create_table(
        "revenue_command_snapshot",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("total_exposure", sa.Numeric(18, 2), nullable=False),
        sa.Column("expected_recovery_30_day", sa.Numeric(18, 2), nullable=False),
        sa.Column("short_term_cash_opportunity", sa.Numeric(18, 2), nullable=False),
        sa.Column("high_risk_claim_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("critical_pre_submission_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("top_aggressive_payers", json_type, nullable=False, server_default=json_array_default),
        sa.Column("top_revenue_loss_drivers", json_type, nullable=False, server_default=json_array_default),
        sa.Column("worklist_priority_summary", json_type, nullable=False, server_default=json_obj_default),
        sa.Column("execution_plan_30_day", json_type, nullable=False, server_default=json_array_default),
        sa.Column("structural_moves_90_day", json_type, nullable=False, server_default=json_array_default),
        sa.Column("aggression_change_alerts", json_type, nullable=False, server_default=json_array_default),
        sa.Column("risk_scoring_version", sa.String(length=50), nullable=False, server_default=sa.text("'1.0'")),
        sa.Column("aggression_scoring_version", sa.String(length=50), nullable=False, server_default=sa.text("'1.0'")),
        sa.Column("pre_submission_scoring_version", sa.String(length=50), nullable=False, server_default=sa.text("'1.0'")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_revenue_command_snapshot_org_id", "revenue_command_snapshot", ["org_id"], unique=False)
    op.create_index("ix_revenue_command_snapshot_generated_at", "revenue_command_snapshot", ["generated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_revenue_command_snapshot_generated_at", table_name="revenue_command_snapshot")
    op.drop_index("ix_revenue_command_snapshot_org_id", table_name="revenue_command_snapshot")
    op.drop_table("revenue_command_snapshot")
