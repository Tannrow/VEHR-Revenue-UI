"""add recon import and reconciliation tables

Revision ID: b2d4e7f9c8a1
Revises: a3b5c7d9e1f2
Create Date: 2026-02-16 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "b2d4e7f9c8a1"
down_revision = "a3b5c7d9e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    json_type = postgresql.JSONB(astext_type=sa.Text()) if dialect == "postgresql" else sa.JSON()

    op.create_table(
        "recon_import_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("era_original_filename", sa.Text(), nullable=False),
        sa.Column("era_storage_path", sa.Text(), nullable=False),
        sa.Column("era_sha256", sa.String(length=64), nullable=False),
        sa.Column("billed_original_filename", sa.Text(), nullable=False),
        sa.Column("billed_storage_path", sa.Text(), nullable=False),
        sa.Column("billed_sha256", sa.String(length=64), nullable=False),
        sa.Column("pages_detected_era", sa.Integer(), nullable=True),
        sa.Column("tables_detected_era", sa.Integer(), nullable=True),
        sa.Column("claims_extracted_era", sa.Integer(), nullable=True),
        sa.Column("lines_extracted_era", sa.Integer(), nullable=True),
        sa.Column("pages_detected_billed", sa.Integer(), nullable=True),
        sa.Column("lines_extracted_billed", sa.Integer(), nullable=True),
        sa.Column("skipped_counts_json", json_type, nullable=True),
        sa.Column("matched_claims", sa.Integer(), nullable=True),
        sa.Column("unmatched_era_claims", sa.Integer(), nullable=True),
        sa.Column("unmatched_billed_claims", sa.Integer(), nullable=True),
        sa.Column("underpaid_claims", sa.Integer(), nullable=True),
        sa.Column("denied_claims", sa.Integer(), nullable=True),
        sa.Column("needs_review_claims", sa.Integer(), nullable=True),
        sa.Column("output_xlsx_path", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "era_sha256", name="uq_recon_import_jobs_org_era_sha256"),
        sa.UniqueConstraint("org_id", "billed_sha256", name="uq_recon_import_jobs_org_billed_sha256"),
    )
    op.create_index("ix_recon_import_jobs_org_created_at", "recon_import_jobs", ["org_id", "created_at"], unique=False)
    op.create_index("ix_recon_import_jobs_status", "recon_import_jobs", ["status"], unique=False)

    op.create_table(
        "era_lines",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=True),
        sa.Column("payer_claim_number", sa.Text(), nullable=True),
        sa.Column("icn", sa.Text(), nullable=True),
        sa.Column("dos_from", sa.Date(), nullable=True),
        sa.Column("dos_to", sa.Date(), nullable=True),
        sa.Column("proc_code", sa.String(length=40), nullable=True),
        sa.Column("units", sa.Numeric(12, 2), nullable=True),
        sa.Column("billed_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("allowed_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("paid_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("adj_code", sa.String(length=40), nullable=True),
        sa.Column("adj_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("source_layout", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["job_id"], ["recon_import_jobs.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_era_lines_job_id", "era_lines", ["job_id"], unique=False)
    op.create_index("ix_era_lines_org_account", "era_lines", ["org_id", "account_id"], unique=False)

    op.create_table(
        "billed_lines",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=True),
        sa.Column("dos_from", sa.Date(), nullable=True),
        sa.Column("dos_to", sa.Date(), nullable=True),
        sa.Column("proc_code", sa.String(length=40), nullable=True),
        sa.Column("units", sa.Numeric(12, 2), nullable=True),
        sa.Column("billed_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["job_id"], ["recon_import_jobs.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_billed_lines_job_id", "billed_lines", ["job_id"], unique=False)
    op.create_index("ix_billed_lines_org_account", "billed_lines", ["org_id", "account_id"], unique=False)

    op.create_table(
        "recon_claim_results",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=True),
        sa.Column("match_status", sa.String(length=24), nullable=False),
        sa.Column("billed_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("paid_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("variance_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("line_count", sa.Integer(), nullable=True),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["job_id"], ["recon_import_jobs.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recon_claim_results_job_status", "recon_claim_results", ["job_id", "match_status"], unique=False)

    op.create_table(
        "recon_line_results",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=True),
        sa.Column("dos_from", sa.Date(), nullable=True),
        sa.Column("dos_to", sa.Date(), nullable=True),
        sa.Column("proc_code", sa.String(length=40), nullable=True),
        sa.Column("billed_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("paid_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("variance_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("match_status", sa.String(length=24), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["job_id"], ["recon_import_jobs.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recon_line_results_job_status", "recon_line_results", ["job_id", "match_status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_recon_line_results_job_status", table_name="recon_line_results")
    op.drop_table("recon_line_results")

    op.drop_index("ix_recon_claim_results_job_status", table_name="recon_claim_results")
    op.drop_table("recon_claim_results")

    op.drop_index("ix_billed_lines_org_account", table_name="billed_lines")
    op.drop_index("ix_billed_lines_job_id", table_name="billed_lines")
    op.drop_table("billed_lines")

    op.drop_index("ix_era_lines_org_account", table_name="era_lines")
    op.drop_index("ix_era_lines_job_id", table_name="era_lines")
    op.drop_table("era_lines")

    op.drop_index("ix_recon_import_jobs_status", table_name="recon_import_jobs")
    op.drop_index("ix_recon_import_jobs_org_created_at", table_name="recon_import_jobs")
    op.drop_table("recon_import_jobs")
