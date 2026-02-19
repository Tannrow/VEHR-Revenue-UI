"""rename claim event billed to service_recorded, add resubmission count and unique constraint

Revision ID: ea1b2c3d4e6b
Revises: e9a1b2c3d4e5
Create Date: 2026-02-18 19:46:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ea1b2c3d4e6b"
down_revision = "e9a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_type t
                    JOIN pg_enum e ON t.oid = e.enumtypid
                    WHERE t.typname = 'claim_event_type' AND e.enumlabel = 'BILLED'
                ) THEN
                    ALTER TYPE claim_event_type RENAME VALUE 'BILLED' TO 'SERVICE_RECORDED';
                END IF;
            END$$;
            """
        )
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("claims")}
    if "resubmission_count" not in existing_columns:
        op.add_column("claims", sa.Column("resubmission_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_constraint("uq_claim_event_per_job", "claim_events", type_="unique")
    op.drop_column("claims", "resubmission_count")

    if dialect == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_type t
                    JOIN pg_enum e ON t.oid = e.enumtypid
                    WHERE t.typname = 'claim_event_type' AND e.enumlabel = 'SERVICE_RECORDED'
                ) THEN
                    ALTER TYPE claim_event_type RENAME VALUE 'SERVICE_RECORDED' TO 'BILLED';
                END IF;
            END$$;
            """
        )
