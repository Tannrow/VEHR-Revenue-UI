"""add msft token fields to user microsoft connections

Revision ID: d4e5f6a7b8c9
Revises: c7f1b2d4e9ab
Create Date: 2026-02-16 13:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "d4e5f6a7b8c9"
down_revision = "c7f1b2d4e9ab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    json_type = postgresql.JSONB(astext_type=sa.Text()) if dialect == "postgresql" else sa.JSON()
    json_default = sa.text("'{}'::jsonb") if dialect == "postgresql" else sa.text("'{}'")

    op.add_column("user_microsoft_connections", sa.Column("access_token_enc", sa.Text(), nullable=True))
    op.add_column("user_microsoft_connections", sa.Column("refresh_token_enc", sa.Text(), nullable=True))
    op.add_column("user_microsoft_connections", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_microsoft_connections", sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_microsoft_connections", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "user_microsoft_connections",
        sa.Column("metadata_json", json_type, nullable=False, server_default=json_default),
    )

    op.alter_column("user_microsoft_connections", "metadata_json", server_default=None)


def downgrade() -> None:
    op.drop_column("user_microsoft_connections", "metadata_json")
    op.drop_column("user_microsoft_connections", "revoked_at")
    op.drop_column("user_microsoft_connections", "connected_at")
    op.drop_column("user_microsoft_connections", "expires_at")
    op.drop_column("user_microsoft_connections", "refresh_token_enc")
    op.drop_column("user_microsoft_connections", "access_token_enc")
