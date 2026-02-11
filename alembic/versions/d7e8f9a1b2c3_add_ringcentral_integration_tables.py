"""add ringcentral integration tables

Revision ID: d7e8f9a1b2c3
Revises: c6d4a2e8f901
Create Date: 2026-02-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d7e8f9a1b2c3"
down_revision = "c6d4a2e8f901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("access_token_enc", sa.Text(), nullable=False),
        sa.Column("refresh_token_enc", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("account_id", sa.String(length=255), nullable=True),
        sa.Column("extension_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "provider", name="uq_integration_tokens_org_provider"),
    )
    op.create_index("ix_integration_tokens_organization_id", "integration_tokens", ["organization_id"])
    op.create_index("ix_integration_tokens_provider", "integration_tokens", ["provider"])

    op.create_table(
        "ringcentral_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("rc_event_id", sa.String(length=255), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("call_id", sa.String(length=255), nullable=True),
        sa.Column("from_number", sa.String(length=64), nullable=True),
        sa.Column("to_number", sa.String(length=64), nullable=True),
        sa.Column("direction", sa.String(length=64), nullable=True),
        sa.Column("disposition", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("raw_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ringcentral_events_organization_id", "ringcentral_events", ["organization_id"])
    op.create_index("ix_ringcentral_events_created_at", "ringcentral_events", ["created_at"])
    op.create_index("ix_ringcentral_events_rc_event_id", "ringcentral_events", ["rc_event_id"])
    op.create_index("ix_ringcentral_events_session_id", "ringcentral_events", ["session_id"])
    op.create_index("ix_ringcentral_events_call_id", "ringcentral_events", ["call_id"])

    op.create_table(
        "reception_call_workflows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("ringcentral_event_id", sa.String(length=36), nullable=False),
        sa.Column("workflow_status", sa.String(length=64), nullable=False, server_default="missed"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("handled_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("followup_task_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["ringcentral_event_id"], ["ringcentral_events.id"]),
        sa.ForeignKeyConstraint(["handled_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["followup_task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "ringcentral_event_id", name="uq_reception_workflow_org_event"),
    )
    op.create_index("ix_reception_call_workflows_organization_id", "reception_call_workflows", ["organization_id"])
    op.create_index("ix_reception_call_workflows_ringcentral_event_id", "reception_call_workflows", ["ringcentral_event_id"])
    op.create_index("ix_reception_call_workflows_handled_by_user_id", "reception_call_workflows", ["handled_by_user_id"])
    op.create_index("ix_reception_call_workflows_followup_task_id", "reception_call_workflows", ["followup_task_id"])


def downgrade() -> None:
    op.drop_index("ix_reception_call_workflows_followup_task_id", table_name="reception_call_workflows")
    op.drop_index("ix_reception_call_workflows_handled_by_user_id", table_name="reception_call_workflows")
    op.drop_index("ix_reception_call_workflows_ringcentral_event_id", table_name="reception_call_workflows")
    op.drop_index("ix_reception_call_workflows_organization_id", table_name="reception_call_workflows")
    op.drop_table("reception_call_workflows")

    op.drop_index("ix_ringcentral_events_call_id", table_name="ringcentral_events")
    op.drop_index("ix_ringcentral_events_session_id", table_name="ringcentral_events")
    op.drop_index("ix_ringcentral_events_rc_event_id", table_name="ringcentral_events")
    op.drop_index("ix_ringcentral_events_created_at", table_name="ringcentral_events")
    op.drop_index("ix_ringcentral_events_organization_id", table_name="ringcentral_events")
    op.drop_table("ringcentral_events")

    op.drop_index("ix_integration_tokens_provider", table_name="integration_tokens")
    op.drop_index("ix_integration_tokens_organization_id", table_name="integration_tokens")
    op.drop_table("integration_tokens")
