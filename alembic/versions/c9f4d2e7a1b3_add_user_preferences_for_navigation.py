"""add user preferences for module navigation and tanner toggle

Revision ID: c9f4d2e7a1b3
Revises: b7e3d1c9a4f2
Create Date: 2026-02-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c9f4d2e7a1b3"
down_revision = "b7e3d1c9a4f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("last_active_module", sa.String(length=64), nullable=True),
        sa.Column("sidebar_collapsed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("copilot_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_user_preferences_org_user"),
    )
    op.create_index("ix_user_preferences_organization_id", "user_preferences", ["organization_id"])
    op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"])
    op.create_index("ix_user_preferences_last_active_module", "user_preferences", ["last_active_module"])


def downgrade() -> None:
    op.drop_index("ix_user_preferences_last_active_module", table_name="user_preferences")
    op.drop_index("ix_user_preferences_user_id", table_name="user_preferences")
    op.drop_index("ix_user_preferences_organization_id", table_name="user_preferences")
    op.drop_table("user_preferences")
