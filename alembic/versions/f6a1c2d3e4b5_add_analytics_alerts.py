"""add analytics alerts

Revision ID: f6a1c2d3e4b5
Revises: 605c0b84d71e
Create Date: 2026-02-15 00:00:04.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "f6a1c2d3e4b5"
down_revision = "605c0b84d71e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    uuid_type = postgresql.UUID(as_uuid=False) if dialect == "postgresql" else sa.String(length=36)
    json_type = postgresql.JSONB(astext_type=sa.Text()) if dialect == "postgresql" else sa.JSON()

    op.create_table(
        "analytics_alerts",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("organization_id", uuid_type, nullable=False),
        sa.Column("alert_type", sa.String(length=40), nullable=False),
        sa.Column("metric_key", sa.String(length=120), nullable=True),
        sa.Column("report_key", sa.String(length=120), nullable=True),
        sa.Column("baseline_window_days", sa.Integer(), nullable=False),
        sa.Column("comparison_period", sa.String(length=80), nullable=False),
        sa.Column("current_range_start", sa.Date(), nullable=False),
        sa.Column("current_range_end", sa.Date(), nullable=False),
        sa.Column("baseline_range_start", sa.Date(), nullable=False),
        sa.Column("baseline_range_end", sa.Date(), nullable=False),
        sa.Column("current_value", sa.Numeric(18, 4), nullable=False),
        sa.Column("baseline_value", sa.Numeric(18, 4), nullable=False),
        sa.Column("delta_value", sa.Numeric(18, 4), nullable=False),
        sa.Column("delta_pct", sa.Numeric(18, 4), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("recommended_actions", json_type, nullable=False),
        sa.Column("context_filters", json_type, nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'open'")),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_analytics_alerts_org_status_created",
        "analytics_alerts",
        ["organization_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ux_analytics_alerts_org_dedupe_key",
        "analytics_alerts",
        ["organization_id", "dedupe_key"],
        unique=True,
    )
    op.create_index(
        "ix_analytics_alerts_org_metric_key",
        "analytics_alerts",
        ["organization_id", "metric_key"],
        unique=False,
    )
    op.create_index(
        "ix_analytics_alerts_org_report_key",
        "analytics_alerts",
        ["organization_id", "report_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_alerts_org_report_key", table_name="analytics_alerts")
    op.drop_index("ix_analytics_alerts_org_metric_key", table_name="analytics_alerts")
    op.drop_index("ux_analytics_alerts_org_dedupe_key", table_name="analytics_alerts")
    op.drop_index("ix_analytics_alerts_org_status_created", table_name="analytics_alerts")
    op.drop_table("analytics_alerts")

