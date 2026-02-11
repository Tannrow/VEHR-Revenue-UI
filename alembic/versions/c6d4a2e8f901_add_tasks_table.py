"""add tasks table

Revision ID: c6d4a2e8f901
Revises: b1f3c2d4e5a6
Create Date: 2026-02-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c6d4a2e8f901"
down_revision = "b1f3c2d4e5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="normal"),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("assigned_to_user_id", sa.String(length=36), nullable=True),
        sa.Column("assigned_team_id", sa.String(length=64), nullable=True),
        sa.Column("related_type", sa.String(length=64), nullable=True),
        sa.Column("related_id", sa.String(length=36), nullable=True),
        sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status in ('open','in_progress','done','canceled')", name="ck_tasks_status"),
        sa.CheckConstraint("priority in ('low','normal','high','urgent')", name="ck_tasks_priority"),
    )

    op.create_index("ix_tasks_organization_id", "tasks", ["organization_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_due_at", "tasks", ["due_at"])
    op.create_index("ix_tasks_assigned_to_user_id", "tasks", ["assigned_to_user_id"])
    op.create_index("ix_tasks_assigned_team_id", "tasks", ["assigned_team_id"])
    op.create_index("ix_tasks_created_by_user_id", "tasks", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_created_by_user_id", table_name="tasks")
    op.drop_index("ix_tasks_assigned_team_id", table_name="tasks")
    op.drop_index("ix_tasks_assigned_to_user_id", table_name="tasks")
    op.drop_index("ix_tasks_due_at", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_organization_id", table_name="tasks")
    op.drop_table("tasks")
