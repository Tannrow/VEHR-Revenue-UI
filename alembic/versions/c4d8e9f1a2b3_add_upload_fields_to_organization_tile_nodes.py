"""add upload metadata fields to organization tile nodes

Revision ID: c4d8e9f1a2b3
Revises: b8f2c6d4a901
Create Date: 2026-02-08 00:00:02.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c4d8e9f1a2b3"
down_revision = "b8f2c6d4a901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organization_tile_nodes",
        sa.Column("storage_key", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "organization_tile_nodes",
        sa.Column("media_type", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "organization_tile_nodes",
        sa.Column("size_bytes", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organization_tile_nodes", "size_bytes")
    op.drop_column("organization_tile_nodes", "media_type")
    op.drop_column("organization_tile_nodes", "storage_key")
