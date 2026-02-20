"""make revenue era structured results immutable after finalization

Revision ID: 5a8c1d2e3f4b
Revises: 1d2f3c4b5a67
Create Date: 2026-02-20 08:55:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "5a8c1d2e3f4b"
down_revision = "1d2f3c4b5a67"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "revenue_era_structured_results",
        sa.Column("processing_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "revenue_era_structured_results",
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "revenue_era_structured_results",
        sa.Column("finalized_by_user_id", sa.Text(), nullable=True),
    )

    op.drop_constraint("uq_revenue_era_structured_results_file", "revenue_era_structured_results", type_="unique")
    op.create_unique_constraint(
        "uq_revenue_era_structured_results_file_version",
        "revenue_era_structured_results",
        ["era_file_id", "processing_version"],
    )

    op.execute(
        sa.text(
            """
            CREATE FUNCTION prevent_revenue_era_structured_results_mutation_after_finalization()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF OLD.finalized_at IS NOT NULL THEN
                    RAISE EXCEPTION 'revenue_era_structured_results row is finalized and immutable'
                        USING ERRCODE = '45000';
                END IF;

                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END;
            $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_revenue_era_structured_results_immutable
            BEFORE UPDATE OR DELETE ON revenue_era_structured_results
            FOR EACH ROW
            EXECUTE FUNCTION prevent_revenue_era_structured_results_mutation_after_finalization();
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_revenue_era_structured_results_immutable ON revenue_era_structured_results;"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_revenue_era_structured_results_mutation_after_finalization();"))

    op.drop_constraint(
        "uq_revenue_era_structured_results_file_version",
        "revenue_era_structured_results",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_revenue_era_structured_results_file",
        "revenue_era_structured_results",
        ["era_file_id"],
    )

    op.drop_column("revenue_era_structured_results", "finalized_by_user_id")
    op.drop_column("revenue_era_structured_results", "finalized_at")
    op.drop_column("revenue_era_structured_results", "processing_version")
