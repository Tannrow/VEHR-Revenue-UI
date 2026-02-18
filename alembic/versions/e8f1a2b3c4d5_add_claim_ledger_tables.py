"""add claim ledger tables

Revision ID: e8f1a2b3c4d5
Revises: d4e5f6a7b8c9
Create Date: 2026-02-18 19:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "e8f1a2b3c4d5"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    json_type = postgresql.JSONB(astext_type=sa.Text()) if dialect == "postgresql" else sa.JSON()

    claim_event_type = sa.Enum(
        "SERVICE_RECORDED",
        "ERA_RECEIVED",
        "PAYMENT",
        "DENIAL",
        "ADJUSTMENT",
        name="claim_event_type",
    )
    claim_ledger_status = sa.Enum(
        "NOT_BILLED",
        "BILLED_NO_RESPONSE",
        "PAID_IN_FULL",
        "PARTIAL_PAYMENT",
        "DENIED",
        "OVERPAID",
        name="claim_ledger_status",
    )

    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("external_claim_id", sa.String(length=120), nullable=True),
        sa.Column("patient_name", sa.String(length=255), nullable=True),
        sa.Column("member_id", sa.String(length=120), nullable=True),
        sa.Column("payer_name", sa.String(length=255), nullable=True),
        sa.Column("dos_from", sa.Date(), nullable=True),
        sa.Column("dos_to", sa.Date(), nullable=True),
        sa.Column("resubmission_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_claims_org_id", "claims", ["org_id"], unique=False)
    op.create_index("ix_claims_external_claim_id", "claims", ["external_claim_id"], unique=False)
    op.create_index("ix_claims_payer_name", "claims", ["payer_name"], unique=False)
    op.create_index("ix_claims_dos_from", "claims", ["dos_from"], unique=False)

    op.create_table(
        "claim_lines",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("cpt_code", sa.String(length=40), nullable=True),
        sa.Column("dos_from", sa.Date(), nullable=True),
        sa.Column("units", sa.Numeric(12, 2), nullable=True),
        sa.Column("expected_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_claim_lines_claim_id", "claim_lines", ["claim_id"], unique=False)
    op.create_index("ix_claim_lines_org_id", "claim_lines", ["org_id"], unique=False)
    op.create_index("ix_claim_lines_cpt_code", "claim_lines", ["cpt_code"], unique=False)
    op.create_index("ix_claim_lines_dos_from", "claim_lines", ["dos_from"], unique=False)

    if dialect == "postgresql":
        claim_event_type.create(bind, checkfirst=True)
        claim_ledger_status.create(bind, checkfirst=True)

    op.create_table(
        "claim_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", claim_event_type, nullable=False),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("source_job_id", sa.String(length=36), nullable=True),
        sa.Column("raw_json", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["source_job_id"], ["recon_import_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("claim_id", "event_type", "source_job_id", name="uq_claim_event_per_job"),
    )
    op.create_index("ix_claim_events_claim_id", "claim_events", ["claim_id"], unique=False)
    op.create_index("ix_claim_events_org_id", "claim_events", ["org_id"], unique=False)
    op.create_index("ix_claim_events_event_date", "claim_events", ["event_date"], unique=False)

    op.create_table(
        "claim_ledgers",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("total_billed", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_paid", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_allowed", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_adjusted", sa.Numeric(14, 2), nullable=True),
        sa.Column("variance", sa.Numeric(14, 2), nullable=True),
        sa.Column("status", claim_ledger_status, nullable=False),
        sa.Column("aging_days", sa.Integer(), nullable=True),
        sa.Column("last_event_date", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("claim_id"),
    )
    op.create_index("ix_claim_ledgers_claim_id", "claim_ledgers", ["claim_id"], unique=False)
    op.create_index("ix_claim_ledgers_org_id", "claim_ledgers", ["org_id"], unique=False)
    op.create_index("ix_claim_ledgers_status", "claim_ledgers", ["status"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_index("ix_claim_ledgers_status", table_name="claim_ledgers")
    op.drop_index("ix_claim_ledgers_org_id", table_name="claim_ledgers")
    op.drop_index("ix_claim_ledgers_claim_id", table_name="claim_ledgers")
    op.drop_table("claim_ledgers")

    op.drop_index("ix_claim_events_event_date", table_name="claim_events")
    op.drop_index("ix_claim_events_org_id", table_name="claim_events")
    op.drop_index("ix_claim_events_claim_id", table_name="claim_events")
    op.drop_constraint("uq_claim_event_per_job", "claim_events", type_="unique")
    op.drop_table("claim_events")

    op.drop_index("ix_claim_lines_cpt_code", table_name="claim_lines")
    op.drop_index("ix_claim_lines_dos_from", table_name="claim_lines")
    op.drop_index("ix_claim_lines_org_id", table_name="claim_lines")
    op.drop_index("ix_claim_lines_claim_id", table_name="claim_lines")
    op.drop_table("claim_lines")

    op.drop_index("ix_claims_dos_from", table_name="claims")
    op.drop_index("ix_claims_payer_name", table_name="claims")
    op.drop_index("ix_claims_external_claim_id", table_name="claims")
    op.drop_index("ix_claims_org_id", table_name="claims")
    op.drop_table("claims")

    if dialect == "postgresql":
        sa.Enum(name="claim_event_type").drop(bind)
        sa.Enum(name="claim_ledger_status").drop(bind)
