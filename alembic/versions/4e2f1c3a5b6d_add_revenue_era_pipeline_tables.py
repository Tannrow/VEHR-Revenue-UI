"""add revenue era pipeline tables

Revision ID: 4e2f1c3a5b6d
Revises: 3c1d5e7f9a02
Create Date: 2026-02-19 16:40:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "4e2f1c3a5b6d"
down_revision = "3c1d5e7f9a02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    json_type = postgresql.JSONB(astext_type=sa.Text()) if dialect == "postgresql" else sa.JSON()

    op.create_table(
        "revenue_era_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("payer_name_raw", sa.Text(), nullable=True),
        sa.Column("received_date", sa.Date(), nullable=True),
        sa.Column("storage_ref", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "sha256", name="uq_revenue_era_files_org_sha"),
    )
    op.create_index("ix_revenue_era_files_org", "revenue_era_files", ["organization_id"], unique=False)
    op.create_index("ix_revenue_era_files_status", "revenue_era_files", ["status"], unique=False)

    op.create_table(
        "revenue_era_extract_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("era_file_id", sa.String(length=36), nullable=False),
        sa.Column("extractor", sa.String(length=50), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("extracted_json", json_type, nullable=False),
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["era_file_id"], ["revenue_era_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_revenue_era_extract_results_file",
        "revenue_era_extract_results",
        ["era_file_id"],
        unique=False,
    )

    op.create_table(
        "revenue_era_structured_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("era_file_id", sa.String(length=36), nullable=False),
        sa.Column("llm", sa.String(length=50), nullable=False),
        sa.Column("deployment", sa.Text(), nullable=False),
        sa.Column("api_version", sa.String(length=50), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("structured_json", json_type, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["era_file_id"], ["revenue_era_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_revenue_era_structured_results_file",
        "revenue_era_structured_results",
        ["era_file_id"],
        unique=False,
    )

    op.create_table(
        "revenue_era_claim_lines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("era_file_id", sa.String(length=36), nullable=False),
        sa.Column("line_index", sa.Integer(), nullable=False),
        sa.Column("claim_ref", sa.Text(), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=True),
        sa.Column("proc_code", sa.String(length=40), nullable=True),
        sa.Column("charge_cents", sa.BigInteger(), nullable=True),
        sa.Column("allowed_cents", sa.BigInteger(), nullable=True),
        sa.Column("paid_cents", sa.BigInteger(), nullable=True),
        sa.Column("adjustments_json", json_type, nullable=True),
        sa.Column("match_status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["era_file_id"], ["revenue_era_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("era_file_id", "line_index", name="uq_revenue_era_claim_lines_file_idx"),
    )
    op.create_index(
        "ix_revenue_era_claim_lines_file",
        "revenue_era_claim_lines",
        ["era_file_id"],
        unique=False,
    )
    op.create_index(
        "ix_revenue_era_claim_lines_match_status",
        "revenue_era_claim_lines",
        ["match_status"],
        unique=False,
    )

    op.create_table(
        "revenue_era_work_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("era_file_id", sa.String(length=36), nullable=False),
        sa.Column("era_claim_line_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("dollars_cents", sa.BigInteger(), nullable=False),
        sa.Column("payer_name", sa.Text(), nullable=False),
        sa.Column("claim_ref", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["era_claim_line_id"], ["revenue_era_claim_lines.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["era_file_id"], ["revenue_era_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_revenue_era_work_items_org_status",
        "revenue_era_work_items",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_revenue_era_work_items_file",
        "revenue_era_work_items",
        ["era_file_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_revenue_era_work_items_file", table_name="revenue_era_work_items")
    op.drop_index("ix_revenue_era_work_items_org_status", table_name="revenue_era_work_items")
    op.drop_table("revenue_era_work_items")

    op.drop_index("ix_revenue_era_claim_lines_match_status", table_name="revenue_era_claim_lines")
    op.drop_index("ix_revenue_era_claim_lines_file", table_name="revenue_era_claim_lines")
    op.drop_table("revenue_era_claim_lines")

    op.drop_index("ix_revenue_era_structured_results_file", table_name="revenue_era_structured_results")
    op.drop_table("revenue_era_structured_results")

    op.drop_index("ix_revenue_era_extract_results_file", table_name="revenue_era_extract_results")
    op.drop_table("revenue_era_extract_results")

    op.drop_index("ix_revenue_era_files_status", table_name="revenue_era_files")
    op.drop_index("ix_revenue_era_files_org", table_name="revenue_era_files")
    op.drop_table("revenue_era_files")
