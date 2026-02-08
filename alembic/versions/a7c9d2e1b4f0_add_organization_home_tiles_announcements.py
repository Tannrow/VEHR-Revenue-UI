"""add organization home tiles and announcements

Revision ID: a7c9d2e1b4f0
Revises: f4d1a8c9b2e3
Create Date: 2026-02-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a7c9d2e1b4f0"
down_revision = "f4d1a8c9b2e3"
branch_labels = None
depends_on = None


LINK_TYPES = ("internal_route", "external_url")


def upgrade() -> None:
    op.create_table(
        "organization_tiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("icon", sa.String(length=60), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("link_type", sa.String(length=30), nullable=False),
        sa.Column("href", sa.String(length=500), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("required_permissions_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f"link_type IN {LINK_TYPES}",
            name="ck_organization_tiles_link_type",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organization_tiles_organization_id", "organization_tiles", ["organization_id"])
    op.create_index("ix_organization_tiles_created_by_user_id", "organization_tiles", ["created_by_user_id"])

    op.create_table(
        "announcements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_announcements_date_window",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_announcements_organization_id", "announcements", ["organization_id"])
    op.create_index("ix_announcements_created_by_user_id", "announcements", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_announcements_created_by_user_id", table_name="announcements")
    op.drop_index("ix_announcements_organization_id", table_name="announcements")
    op.drop_table("announcements")

    op.drop_index("ix_organization_tiles_created_by_user_id", table_name="organization_tiles")
    op.drop_index("ix_organization_tiles_organization_id", table_name="organization_tiles")
    op.drop_table("organization_tiles")
