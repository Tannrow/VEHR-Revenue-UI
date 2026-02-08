"""add organization tile nodes for in-page workspace folders/files

Revision ID: b8f2c6d4a901
Revises: a7c9d2e1b4f0
Create Date: 2026-02-08 00:00:01.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b8f2c6d4a901"
down_revision = "a7c9d2e1b4f0"
branch_labels = None
depends_on = None


NODE_TYPES = ("folder", "file")


def upgrade() -> None:
    op.create_table(
        "organization_tile_nodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("tile_id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("node_type", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f"node_type IN {NODE_TYPES}",
            name="ck_organization_tile_nodes_node_type",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["tile_id"], ["organization_tiles.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["organization_tile_nodes.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_organization_tile_nodes_organization_id",
        "organization_tile_nodes",
        ["organization_id"],
    )
    op.create_index(
        "ix_organization_tile_nodes_tile_id",
        "organization_tile_nodes",
        ["tile_id"],
    )
    op.create_index(
        "ix_organization_tile_nodes_parent_id",
        "organization_tile_nodes",
        ["parent_id"],
    )
    op.create_index(
        "ix_organization_tile_nodes_created_by_user_id",
        "organization_tile_nodes",
        ["created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_organization_tile_nodes_created_by_user_id", table_name="organization_tile_nodes")
    op.drop_index("ix_organization_tile_nodes_parent_id", table_name="organization_tile_nodes")
    op.drop_index("ix_organization_tile_nodes_tile_id", table_name="organization_tile_nodes")
    op.drop_index("ix_organization_tile_nodes_organization_id", table_name="organization_tile_nodes")
    op.drop_table("organization_tile_nodes")
