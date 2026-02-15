"""add weekly executive reporting foundation tables

Revision ID: e9c2b7d4f901
Revises: d2b7f1c8a4e9
Create Date: 2026-02-15 00:00:02.000000
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "e9c2b7d4f901"
down_revision = "d2b7f1c8a4e9"
branch_labels = None
depends_on = None


_ALLOWED_ROLES = ["admin", "office_manager", "compliance"]
_METRIC_SEEDS = (
    ("active_clients", "Active client census.", "operations", "daily", "rpt_kpi_daily"),
    ("new_admissions_week", "New admissions for the week.", "operations", "daily", "rpt_kpi_daily"),
    ("discharges_week", "Discharges for the week.", "operations", "daily", "rpt_kpi_daily"),
    ("attendance_rate_week", "Attendance rate for the week.", "operations", "daily", "rpt_kpi_daily"),
    ("no_show_rate_week", "No-show rate for the week.", "operations", "daily", "rpt_kpi_daily"),
    ("encounters_week", "Encounter volume for the week.", "operations", "daily", "rpt_kpi_daily"),
    ("charges_week", "Charges generated in the week.", "financial", "daily", "rpt_kpi_daily"),
    ("claims_submitted_week", "Claims submitted in the week.", "financial", "daily", "rpt_kpi_daily"),
    ("claims_paid_week", "Claims paid in the week.", "financial", "daily", "rpt_kpi_daily"),
    ("denial_rate_week", "Claims denial rate in the week.", "financial", "daily", "rpt_kpi_daily"),
    ("ar_balance_total", "Total accounts receivable balance.", "financial", "snapshot", "rpt_kpi_snapshot"),
    ("ar_over_30", "A/R balance over 30 days.", "financial", "snapshot", "rpt_kpi_snapshot"),
    ("ar_over_60", "A/R balance over 60 days.", "financial", "snapshot", "rpt_kpi_snapshot"),
    ("ar_over_90", "A/R balance over 90 days.", "financial", "snapshot", "rpt_kpi_snapshot"),
    ("unsigned_notes_over_24h", "Unsigned notes older than 24 hours.", "compliance", "daily", "rpt_kpi_daily"),
    ("unsigned_notes_over_72h", "Unsigned notes older than 72 hours.", "compliance", "daily", "rpt_kpi_daily"),
)


def _drop_legacy_views() -> None:
    op.execute("DROP VIEW IF EXISTS rpt_kpi_daily")
    op.execute("DROP VIEW IF EXISTS rpt_kpi_snapshot")


def _seed_analytics_metrics() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name
    if dialect == "postgresql":
        statement = sa.text(
            """
            INSERT INTO analytics_metrics (
                metric_key,
                description,
                category,
                grain,
                backing_table,
                allowed_roles,
                created_at,
                updated_at
            )
            VALUES (
                :metric_key,
                :description,
                :category,
                :grain,
                :backing_table,
                CAST(:allowed_roles AS JSONB),
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT(metric_key) DO UPDATE SET
                description = excluded.description,
                category = excluded.category,
                grain = excluded.grain,
                backing_table = excluded.backing_table,
                allowed_roles = excluded.allowed_roles,
                updated_at = CURRENT_TIMESTAMP
            """
        )
    else:
        statement = sa.text(
            """
            INSERT INTO analytics_metrics (
                metric_key,
                description,
                category,
                grain,
                backing_table,
                allowed_roles,
                created_at,
                updated_at
            )
            VALUES (
                :metric_key,
                :description,
                :category,
                :grain,
                :backing_table,
                :allowed_roles,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT(metric_key) DO UPDATE SET
                description = excluded.description,
                category = excluded.category,
                grain = excluded.grain,
                backing_table = excluded.backing_table,
                allowed_roles = excluded.allowed_roles,
                updated_at = CURRENT_TIMESTAMP
            """
        )

    for metric_key, description, category, grain, backing_table in _METRIC_SEEDS:
        conn.execute(
            statement,
            {
                "metric_key": metric_key,
                "description": description,
                "category": category,
                "grain": grain,
                "backing_table": backing_table,
                "allowed_roles": json.dumps(_ALLOWED_ROLES),
            },
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    dialect = bind.dialect.name

    uuid_type = postgresql.UUID(as_uuid=False) if dialect == "postgresql" else sa.String(length=36)
    json_type = postgresql.JSONB(astext_type=sa.Text()) if dialect == "postgresql" else sa.JSON()

    _drop_legacy_views()

    if "analytics_metrics" in inspector.get_table_names():
        op.drop_table("analytics_metrics")

    op.create_table(
        "analytics_metrics",
        sa.Column("metric_key", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("grain", sa.Text(), nullable=False),
        sa.Column("backing_table", sa.Text(), nullable=False),
        sa.Column("allowed_roles", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("metric_key"),
    )
    op.create_index("ix_analytics_metrics_category", "analytics_metrics", ["category"])
    op.create_index("ix_analytics_metrics_grain", "analytics_metrics", ["grain"])

    op.create_table(
        "rpt_kpi_daily",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("tenant_id", uuid_type, nullable=False),
        sa.Column("kpi_date", sa.Date(), nullable=False),
        sa.Column("metric_key", sa.Text(), nullable=False),
        sa.Column("value_num", sa.Numeric(18, 4), nullable=True),
        sa.Column("value_json", json_type, nullable=True),
        sa.Column("facility_id", uuid_type, nullable=True),
        sa.Column("program_id", uuid_type, nullable=True),
        sa.Column("provider_id", uuid_type, nullable=True),
        sa.Column("payer_id", uuid_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rpt_kpi_daily_tenant_id", "rpt_kpi_daily", ["tenant_id"])
    op.create_index("ix_rpt_kpi_daily_kpi_date", "rpt_kpi_daily", ["kpi_date"])
    op.create_index("ix_rpt_kpi_daily_metric_key", "rpt_kpi_daily", ["metric_key"])
    op.create_index(
        "ix_rpt_kpi_daily_tenant_metric_date",
        "rpt_kpi_daily",
        ["tenant_id", "metric_key", "kpi_date"],
    )

    op.create_table(
        "rpt_kpi_snapshot",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("tenant_id", uuid_type, nullable=False),
        sa.Column("as_of_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metric_key", sa.Text(), nullable=False),
        sa.Column("value_num", sa.Numeric(18, 4), nullable=True),
        sa.Column("value_json", json_type, nullable=True),
        sa.Column("facility_id", uuid_type, nullable=True),
        sa.Column("program_id", uuid_type, nullable=True),
        sa.Column("provider_id", uuid_type, nullable=True),
        sa.Column("payer_id", uuid_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rpt_kpi_snapshot_tenant_id", "rpt_kpi_snapshot", ["tenant_id"])
    op.create_index("ix_rpt_kpi_snapshot_as_of_ts", "rpt_kpi_snapshot", ["as_of_ts"])
    op.create_index("ix_rpt_kpi_snapshot_metric_key", "rpt_kpi_snapshot", ["metric_key"])
    op.create_index(
        "ix_rpt_kpi_snapshot_tenant_metric_ts",
        "rpt_kpi_snapshot",
        ["tenant_id", "metric_key", "as_of_ts"],
    )

    op.create_table(
        "generated_reports",
        sa.Column("report_id", uuid_type, nullable=False),
        sa.Column("report_key", sa.Text(), nullable=False),
        sa.Column("tenant_id", uuid_type, nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_by", uuid_type, nullable=True),
        sa.Column("content_json", json_type, nullable=False),
        sa.PrimaryKeyConstraint("report_id"),
    )
    op.create_index("ix_generated_reports_report_key", "generated_reports", ["report_key"])
    op.create_index("ix_generated_reports_tenant_id", "generated_reports", ["tenant_id"])
    op.create_index(
        "ix_generated_reports_tenant_report_generated",
        "generated_reports",
        ["tenant_id", "report_key", "generated_at"],
    )

    _seed_analytics_metrics()


def downgrade() -> None:
    op.drop_index("ix_generated_reports_tenant_report_generated", table_name="generated_reports")
    op.drop_index("ix_generated_reports_tenant_id", table_name="generated_reports")
    op.drop_index("ix_generated_reports_report_key", table_name="generated_reports")
    op.drop_table("generated_reports")

    op.drop_index("ix_rpt_kpi_snapshot_tenant_metric_ts", table_name="rpt_kpi_snapshot")
    op.drop_index("ix_rpt_kpi_snapshot_metric_key", table_name="rpt_kpi_snapshot")
    op.drop_index("ix_rpt_kpi_snapshot_as_of_ts", table_name="rpt_kpi_snapshot")
    op.drop_index("ix_rpt_kpi_snapshot_tenant_id", table_name="rpt_kpi_snapshot")
    op.drop_table("rpt_kpi_snapshot")

    op.drop_index("ix_rpt_kpi_daily_tenant_metric_date", table_name="rpt_kpi_daily")
    op.drop_index("ix_rpt_kpi_daily_metric_key", table_name="rpt_kpi_daily")
    op.drop_index("ix_rpt_kpi_daily_kpi_date", table_name="rpt_kpi_daily")
    op.drop_index("ix_rpt_kpi_daily_tenant_id", table_name="rpt_kpi_daily")
    op.drop_table("rpt_kpi_daily")

    op.drop_index("ix_analytics_metrics_grain", table_name="analytics_metrics")
    op.drop_index("ix_analytics_metrics_category", table_name="analytics_metrics")
    op.drop_table("analytics_metrics")

    op.create_table(
        "analytics_metrics",
        sa.Column("metric_key", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("backing_view", sa.String(length=120), nullable=False),
        sa.Column("allowed_roles", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("default_grain", sa.String(length=32), nullable=False, server_default=sa.text("'day'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("metric_key"),
    )

    op.execute(
        """
        CREATE VIEW rpt_kpi_daily AS
        SELECT
            CAST(NULL AS DATE) AS date,
            CAST(NULL AS VARCHAR(120)) AS metric_key,
            CAST(NULL AS DOUBLE PRECISION) AS value_num,
            CAST(NULL AS VARCHAR(36)) AS tenant_id,
            CAST(NULL AS VARCHAR(36)) AS facility_id,
            CAST(NULL AS VARCHAR(36)) AS program_id
        WHERE 1 = 0
        """
    )
    op.execute(
        """
        CREATE VIEW rpt_kpi_snapshot AS
        SELECT
            CAST(NULL AS TIMESTAMP) AS as_of_ts,
            CAST(NULL AS VARCHAR(120)) AS metric_key,
            CAST(NULL AS DOUBLE PRECISION) AS value_num,
            CAST(NULL AS VARCHAR(36)) AS tenant_id,
            CAST(NULL AS VARCHAR(36)) AS facility_id,
            CAST(NULL AS VARCHAR(36)) AS program_id
        WHERE 1 = 0
        """
    )
