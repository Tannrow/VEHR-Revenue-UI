"""add patient chart foundation tables

Revision ID: 7f3a6b2c9d10
Revises: c4d8e9f1a2b3
Create Date: 2026-02-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7f3a6b2c9d10"
down_revision = "c4d8e9f1a2b3"
branch_labels = None
depends_on = None


SERVICE_CATEGORIES = ("intake", "sud", "mh", "psych", "cm")
EPISODE_STATUSES = ("active", "discharged")
CARE_TEAM_ROLES = (
    "counselor",
    "psych_provider",
    "case_manager",
    "supervisor",
    "primary_coordinator",
)
REQUIREMENT_TYPES = (
    "missing_demographics",
    "missing_insurance",
    "missing_consent",
    "missing_assessment",
    "unsigned_note",
    "expiring_roi",
)
REQUIREMENT_STATUSES = ("open", "resolved")
TREATMENT_STAGES = (
    "intake_started",
    "paperwork_completed",
    "assessment_completed",
    "enrolled",
    "active_treatment",
    "step_down_transition",
    "discharge_planning",
    "discharged",
)


def upgrade() -> None:
    op.create_table(
        "episodes_of_care",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("admit_date", sa.Date(), nullable=False),
        sa.Column("discharge_date", sa.Date(), nullable=True),
        sa.Column("referral_source", sa.String(length=200), nullable=True),
        sa.Column("reason_for_admission", sa.Text(), nullable=True),
        sa.Column("primary_service_category", sa.String(length=20), nullable=False),
        sa.Column("court_involved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("discharge_disposition", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f"primary_service_category IN {SERVICE_CATEGORIES}",
            name="ck_episodes_of_care_primary_service_category",
        ),
        sa.CheckConstraint(
            f"status IN {EPISODE_STATUSES}",
            name="ck_episodes_of_care_status",
        ),
        sa.CheckConstraint(
            "discharge_date IS NULL OR discharge_date >= admit_date",
            name="ck_episodes_of_care_date_window",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_episodes_of_care_organization_id", "episodes_of_care", ["organization_id"])
    op.create_index("ix_episodes_of_care_patient_id", "episodes_of_care", ["patient_id"])
    op.create_index("ix_episodes_of_care_status", "episodes_of_care", ["status"])

    op.create_table(
        "patient_care_team",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("episode_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f"role IN {CARE_TEAM_ROLES}",
            name="ck_patient_care_team_role",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes_of_care.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "episode_id",
            "role",
            "user_id",
            name="uq_patient_care_team_episode_role_user",
        ),
    )
    op.create_index("ix_patient_care_team_organization_id", "patient_care_team", ["organization_id"])
    op.create_index("ix_patient_care_team_patient_id", "patient_care_team", ["patient_id"])
    op.create_index("ix_patient_care_team_episode_id", "patient_care_team", ["episode_id"])
    op.create_index("ix_patient_care_team_user_id", "patient_care_team", ["user_id"])

    op.create_table(
        "patient_requirements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("episode_id", sa.String(length=36), nullable=False),
        sa.Column("requirement_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'open'")),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("auto_generated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f"requirement_type IN {REQUIREMENT_TYPES}",
            name="ck_patient_requirements_requirement_type",
        ),
        sa.CheckConstraint(
            f"status IN {REQUIREMENT_STATUSES}",
            name="ck_patient_requirements_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes_of_care.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_patient_requirements_organization_id", "patient_requirements", ["organization_id"])
    op.create_index("ix_patient_requirements_patient_id", "patient_requirements", ["patient_id"])
    op.create_index("ix_patient_requirements_episode_id", "patient_requirements", ["episode_id"])
    op.create_index("ix_patient_requirements_status", "patient_requirements", ["status"])

    op.create_table(
        "patient_treatment_stage",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("episode_id", sa.String(length=36), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f"stage IN {TREATMENT_STAGES}",
            name="ck_patient_treatment_stage_stage",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes_of_care.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("episode_id", name="uq_patient_treatment_stage_episode"),
    )
    op.create_index(
        "ix_patient_treatment_stage_organization_id",
        "patient_treatment_stage",
        ["organization_id"],
    )
    op.create_index("ix_patient_treatment_stage_patient_id", "patient_treatment_stage", ["patient_id"])
    op.create_index("ix_patient_treatment_stage_episode_id", "patient_treatment_stage", ["episode_id"])

    op.create_table(
        "patient_treatment_stage_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("episode_id", sa.String(length=36), nullable=False),
        sa.Column("patient_treatment_stage_id", sa.String(length=36), nullable=True),
        sa.Column("from_stage", sa.String(length=40), nullable=True),
        sa.Column("to_stage", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f"from_stage IS NULL OR from_stage IN {TREATMENT_STAGES}",
            name="ck_patient_treatment_stage_events_from_stage",
        ),
        sa.CheckConstraint(
            f"to_stage IN {TREATMENT_STAGES}",
            name="ck_patient_treatment_stage_events_to_stage",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes_of_care.id"]),
        sa.ForeignKeyConstraint(["patient_treatment_stage_id"], ["patient_treatment_stage.id"]),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_patient_treatment_stage_events_organization_id",
        "patient_treatment_stage_events",
        ["organization_id"],
    )
    op.create_index(
        "ix_patient_treatment_stage_events_patient_id",
        "patient_treatment_stage_events",
        ["patient_id"],
    )
    op.create_index(
        "ix_patient_treatment_stage_events_episode_id",
        "patient_treatment_stage_events",
        ["episode_id"],
    )
    op.create_index(
        "ix_patient_treatment_stage_events_stage_id",
        "patient_treatment_stage_events",
        ["patient_treatment_stage_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_patient_treatment_stage_events_stage_id", table_name="patient_treatment_stage_events")
    op.drop_index("ix_patient_treatment_stage_events_episode_id", table_name="patient_treatment_stage_events")
    op.drop_index("ix_patient_treatment_stage_events_patient_id", table_name="patient_treatment_stage_events")
    op.drop_index(
        "ix_patient_treatment_stage_events_organization_id",
        table_name="patient_treatment_stage_events",
    )
    op.drop_table("patient_treatment_stage_events")

    op.drop_index("ix_patient_treatment_stage_episode_id", table_name="patient_treatment_stage")
    op.drop_index("ix_patient_treatment_stage_patient_id", table_name="patient_treatment_stage")
    op.drop_index("ix_patient_treatment_stage_organization_id", table_name="patient_treatment_stage")
    op.drop_table("patient_treatment_stage")

    op.drop_index("ix_patient_requirements_status", table_name="patient_requirements")
    op.drop_index("ix_patient_requirements_episode_id", table_name="patient_requirements")
    op.drop_index("ix_patient_requirements_patient_id", table_name="patient_requirements")
    op.drop_index("ix_patient_requirements_organization_id", table_name="patient_requirements")
    op.drop_table("patient_requirements")

    op.drop_index("ix_patient_care_team_user_id", table_name="patient_care_team")
    op.drop_index("ix_patient_care_team_episode_id", table_name="patient_care_team")
    op.drop_index("ix_patient_care_team_patient_id", table_name="patient_care_team")
    op.drop_index("ix_patient_care_team_organization_id", table_name="patient_care_team")
    op.drop_table("patient_care_team")

    op.drop_index("ix_episodes_of_care_status", table_name="episodes_of_care")
    op.drop_index("ix_episodes_of_care_patient_id", table_name="episodes_of_care")
    op.drop_index("ix_episodes_of_care_organization_id", table_name="episodes_of_care")
    op.drop_table("episodes_of_care")
