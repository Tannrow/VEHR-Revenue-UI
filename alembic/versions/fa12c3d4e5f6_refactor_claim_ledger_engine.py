"""refactor claim ledger engine and enums

Revision ID: fa12c3d4e5f6
Revises: f7c3a9b1d2e4
Create Date: 2026-02-18 21:50:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "fa12c3d4e5f6"
down_revision = "f7c3a9b1d2e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    claim_status_enum = sa.Enum("OPEN", "PARTIAL", "PAID", "DENIED", name="claim_status")
    if dialect == "postgresql":
        claim_status_enum.create(bind, checkfirst=True)

    op.add_column(
        "claims",
        sa.Column(
            "status",
            claim_status_enum,
            nullable=False,
            server_default="OPEN",
        ),
    )
    op.create_index("ix_claims_status", "claims", ["status"], unique=False)

    op.add_column(
        "claim_lines",
        sa.Column("billed_amount", sa.Numeric(14, 2), nullable=True),
    )

    op.add_column(
        "claim_events",
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "claim_events",
        sa.Column("job_id", sa.String(length=64), nullable=True),
    )
    op.execute("UPDATE claim_events SET job_id = source_job_id")
    op.drop_constraint("uq_claim_event_per_job", "claim_events", type_="unique")
    op.create_unique_constraint(
        "uq_claim_event_per_job",
        "claim_events",
        ["claim_id", "event_type", "job_id"],
    )

    op.drop_index("ix_claim_ledgers_status", table_name="claim_ledgers")
    op.add_column(
        "claim_ledgers",
        sa.Column(
            "status_new",
            claim_status_enum,
            nullable=True,
            server_default="OPEN",
        ),
    )
    op.execute(
        """
        UPDATE claim_ledgers
        SET status_new = CASE status
            WHEN 'PAID_IN_FULL' THEN 'PAID'
            WHEN 'OVERPAID' THEN 'PAID'
            WHEN 'PARTIAL_PAYMENT' THEN 'PARTIAL'
            WHEN 'DENIED' THEN 'DENIED'
            ELSE 'OPEN'
        END
        """
    )
    op.alter_column("claim_ledgers", "status_new", nullable=False, server_default="OPEN")
    op.drop_column("claim_ledgers", "status")
    op.alter_column("claim_ledgers", "status_new", new_column_name="status")
    op.create_index("ix_claim_ledgers_status", "claim_ledgers", ["status"], unique=False)

    op.execute(
        """
        UPDATE claims
        SET status = cl.status
        FROM claim_ledgers cl
        WHERE cl.claim_id = claims.id
        """
    )

    op.alter_column("claims", "status", server_default=None)
    op.alter_column("claim_ledgers", "status", server_default=None)

    if dialect == "postgresql":
        op.execute("DROP TYPE IF EXISTS claim_ledger_status")


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    claim_ledger_status_enum = sa.Enum(
        "NOT_BILLED",
        "BILLED_NO_RESPONSE",
        "PAID_IN_FULL",
        "PARTIAL_PAYMENT",
        "DENIED",
        "OVERPAID",
        name="claim_ledger_status",
    )
    if dialect == "postgresql":
        claim_ledger_status_enum.create(bind, checkfirst=True)

    op.drop_index("ix_claim_ledgers_status", table_name="claim_ledgers")
    op.add_column(
        "claim_ledgers",
        sa.Column(
            "status_old",
            claim_ledger_status_enum,
            nullable=True,
            server_default="NOT_BILLED",
        ),
    )
    op.execute(
        """
        UPDATE claim_ledgers
        SET status_old = CASE status
            WHEN 'PAID' THEN 'PAID_IN_FULL'
            WHEN 'PARTIAL' THEN 'PARTIAL_PAYMENT'
            WHEN 'DENIED' THEN 'DENIED'
            ELSE 'NOT_BILLED'
        END
        """
    )
    op.drop_column("claim_ledgers", "status")
    op.alter_column(
        "claim_ledgers",
        "status_old",
        new_column_name="status",
        existing_type=claim_ledger_status_enum,
        nullable=False,
        server_default="NOT_BILLED",
    )
    op.create_index("ix_claim_ledgers_status", "claim_ledgers", ["status"], unique=False)
    op.alter_column("claim_ledgers", "status", server_default=None)

    op.drop_constraint("uq_claim_event_per_job", "claim_events", type_="unique")
    op.create_unique_constraint(
        "uq_claim_event_per_job",
        "claim_events",
        ["claim_id", "event_type", "source_job_id"],
    )
    op.drop_column("claim_events", "job_id")
    op.drop_column("claim_events", "amount")

    op.drop_column("claim_lines", "billed_amount")

    op.drop_index("ix_claims_status", table_name="claims")
    op.drop_column("claims", "status")

    claim_status = sa.Enum("OPEN", "PARTIAL", "PAID", "DENIED", name="claim_status")
    if dialect == "postgresql":
        claim_status.drop(bind, checkfirst=True)
