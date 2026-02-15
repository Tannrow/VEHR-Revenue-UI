"""add reporting materialized views

Revision ID: 605c0b84d71e
Revises: e9c2b7d4f901
Create Date: 2026-02-15 00:00:03.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "605c0b84d71e"
down_revision = "e9c2b7d4f901"
branch_labels = None
depends_on = None


def _create_supporting_indexes() -> None:
    # Refreshing materializations relies on these columns. Keep indexes narrow and multi-tenant safe.
    op.create_index(
        "ix_encounters_org_start_time",
        "encounters",
        ["organization_id", "start_time"],
        unique=False,
    )
    op.create_index(
        "ix_episodes_of_care_org_admit_date",
        "episodes_of_care",
        ["organization_id", "admit_date"],
        unique=False,
    )
    op.create_index(
        "ix_episodes_of_care_org_discharge_date",
        "episodes_of_care",
        ["organization_id", "discharge_date"],
        unique=False,
    )


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    _create_supporting_indexes()

    # Materialized views are Postgres-specific. For SQLite dev environments, keep analytics functional
    # via the existing rpt_kpi_* tables (populated externally).
    if dialect != "postgresql":
        return

    op.execute("CREATE SCHEMA IF NOT EXISTS reporting")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS reporting.mv_kpi_daily_core")
    op.execute(
        """
        CREATE MATERIALIZED VIEW reporting.mv_kpi_daily_core AS
        SELECT
            src.tenant_id AS tenant_id,
            src.kpi_date AS kpi_date,
            src.metric_key AS metric_key,
            CAST(src.value_num AS NUMERIC(18, 4)) AS value_num,
            NULL::JSONB AS value_json,
            NULL::UUID AS facility_id,
            NULL::UUID AS program_id,
            NULL::UUID AS provider_id,
            NULL::UUID AS payer_id
        FROM (
            SELECT
                encounters.organization_id::uuid AS tenant_id,
                encounters.start_time::date AS kpi_date,
                'encounters_week'::text AS metric_key,
                COUNT(*)::numeric AS value_num
            FROM encounters
            WHERE encounters.organization_id IS NOT NULL
            GROUP BY encounters.organization_id::uuid, encounters.start_time::date

            UNION ALL

            SELECT
                episodes_of_care.organization_id::uuid AS tenant_id,
                episodes_of_care.admit_date AS kpi_date,
                'new_admissions_week'::text AS metric_key,
                COUNT(*)::numeric AS value_num
            FROM episodes_of_care
            WHERE episodes_of_care.organization_id IS NOT NULL
            GROUP BY episodes_of_care.organization_id::uuid, episodes_of_care.admit_date

            UNION ALL

            SELECT
                episodes_of_care.organization_id::uuid AS tenant_id,
                episodes_of_care.discharge_date AS kpi_date,
                'discharges_week'::text AS metric_key,
                COUNT(*)::numeric AS value_num
            FROM episodes_of_care
            WHERE episodes_of_care.organization_id IS NOT NULL
              AND episodes_of_care.discharge_date IS NOT NULL
            GROUP BY episodes_of_care.organization_id::uuid, episodes_of_care.discharge_date
        ) AS src
        WITH NO DATA
        """
    )

    # Required for CONCURRENTLY refresh.
    op.execute(
        """
        CREATE UNIQUE INDEX ux_reporting_mv_kpi_daily_core
        ON reporting.mv_kpi_daily_core (tenant_id, metric_key, kpi_date)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_reporting_mv_kpi_daily_core_metric_date
        ON reporting.mv_kpi_daily_core (metric_key, kpi_date)
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute("DROP MATERIALIZED VIEW IF EXISTS reporting.mv_kpi_daily_core")
        op.execute("DROP SCHEMA IF EXISTS reporting")

    op.drop_index("ix_episodes_of_care_org_discharge_date", table_name="episodes_of_care")
    op.drop_index("ix_episodes_of_care_org_admit_date", table_name="episodes_of_care")
    op.drop_index("ix_encounters_org_start_time", table_name="encounters")

