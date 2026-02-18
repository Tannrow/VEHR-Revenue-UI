"""add organizations and auth models

Revision ID: 7b2d7b3c1a45
Revises: 59024797cfde
Create Date: 2026-02-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7b2d7b3c1a45"
down_revision = "59024797cfde"
branch_labels = None
depends_on = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _foreign_key_exists(inspector: sa.Inspector, table_name: str, fk_name: str) -> bool:
    return any(fk.get("name") == fk_name for fk in inspector.get_foreign_keys(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    dialect_name = bind.dialect.name

    if not _table_exists(inspector, "organizations"):
        op.create_table(
            "organizations",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "users"):
        op.create_table(
            "users",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("full_name", sa.String(length=200), nullable=True),
            sa.Column("hashed_password", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "users") and not _index_exists(inspector, "users", "ix_users_email"):
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "organization_memberships"):
        op.create_table(
            "organization_memberships",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("organization_id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("role", sa.String(length=50), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "user_id", name="uq_org_user"),
        )

    for table in ("patients", "encounters", "form_templates", "form_submissions", "audit_events"):
        inspector = sa.inspect(bind)
        if _table_exists(inspector, table) and not _column_exists(inspector, table, "organization_id"):
            op.add_column(table, sa.Column("organization_id", sa.String(length=36), nullable=True))

        inspector = sa.inspect(bind)
        fk_name = f"fk_{table}_organization_id"
        if _table_exists(inspector, table) and not _foreign_key_exists(inspector, table, fk_name):
            op.create_foreign_key(
                fk_name,
                table,
                "organizations",
                ["organization_id"],
                ["id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    dialect_name = bind.dialect.name

    for table in ("audit_events", "form_submissions", "form_templates", "encounters", "patients"):
        inspector = sa.inspect(bind)
        if not _table_exists(inspector, table):
            continue

        fk_name = f"fk_{table}_organization_id"
        if _foreign_key_exists(inspector, table, fk_name):
            op.drop_constraint(fk_name, table, type_="foreignkey")

        inspector = sa.inspect(bind)
        if _column_exists(inspector, table, "organization_id"):
            op.drop_column(table, "organization_id")

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "organization_memberships"):
        op.drop_table("organization_memberships")

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "users"):
        if _index_exists(inspector, "users", "ix_users_email"):
            op.drop_index("ix_users_email", table_name="users")
        op.drop_table("users")

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "organizations"):
        op.drop_table("organizations")
