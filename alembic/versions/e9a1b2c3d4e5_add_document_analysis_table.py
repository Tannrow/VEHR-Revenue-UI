"""add document analysis table

Revision ID: e9a1b2c3d4e5
Revises: e8f1a2b3c4d5
Create Date: 2026-02-18 19:24:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "e9a1b2c3d4e5"
down_revision = "e8f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    json_type = postgresql.JSONB(astext_type=sa.Text()) if dialect == "postgresql" else sa.JSON()
    doc_type_enum = postgresql.ENUM("ERA", "BILLED", name="document_type", create_type=False)
    if dialect == "postgresql":
        doc_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "document_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("document_type", doc_type_enum, nullable=False),
        sa.Column("raw_json", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["job_id"], ["recon_import_jobs.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_analyses_org_id", "document_analyses", ["org_id"], unique=False)
    op.create_index("ix_document_analyses_job_id", "document_analyses", ["job_id"], unique=False)
    op.create_index("ix_document_analyses_document_type", "document_analyses", ["document_type"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_index("ix_document_analyses_document_type", table_name="document_analyses")
    op.drop_index("ix_document_analyses_job_id", table_name="document_analyses")
    op.drop_index("ix_document_analyses_org_id", table_name="document_analyses")
    op.drop_table("document_analyses")

    if dialect == "postgresql":
        sa.Enum(name="document_type").drop(bind)
