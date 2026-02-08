"""add services, enrollments, and patient notes

Revision ID: e7c4f1a2b3d4
Revises: d4f3b2a1c9e0
Create Date: 2026-02-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e7c4f1a2b3d4"
down_revision = "d4f3b2a1c9e0"
branch_labels = None
depends_on = None


SERVICE_CATEGORIES = ("intake", "sud", "mh", "psych", "cm")
ENROLLMENT_STATUSES = ("active", "paused", "discharged")
NOTE_VISIBILITIES = ("clinical_only", "legal_and_clinical")


def upgrade() -> None:
    op.create_table(
        "services",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f"category IN {SERVICE_CATEGORIES}",
            name="ck_services_category",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "code", name="uq_services_org_code"),
    )
    op.create_index("ix_services_organization_id", "services", ["organization_id"])

    op.create_table(
        "patient_service_enrollments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("service_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("assigned_staff_user_id", sa.String(length=36), nullable=True),
        sa.Column("reporting_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f"status IN {ENROLLMENT_STATUSES}",
            name="ck_patient_service_enrollments_status",
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_patient_service_enrollments_date_window",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
        sa.ForeignKeyConstraint(["assigned_staff_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_patient_service_enrollments_organization_id",
        "patient_service_enrollments",
        ["organization_id"],
    )
    op.create_index(
        "ix_patient_service_enrollments_patient_id",
        "patient_service_enrollments",
        ["patient_id"],
    )
    op.create_index(
        "ix_patient_service_enrollments_service_id",
        "patient_service_enrollments",
        ["service_id"],
    )
    op.create_index(
        "ix_patient_service_enrollments_assigned_staff_user_id",
        "patient_service_enrollments",
        ["assigned_staff_user_id"],
    )

    op.create_table(
        "patient_notes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("primary_service_id", sa.String(length=36), nullable=False),
        sa.Column("visibility", sa.String(length=30), nullable=False, server_default="clinical_only"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f"visibility IN {NOTE_VISIBILITIES}",
            name="ck_patient_notes_visibility",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["primary_service_id"], ["services.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_patient_notes_organization_id", "patient_notes", ["organization_id"])
    op.create_index("ix_patient_notes_patient_id", "patient_notes", ["patient_id"])
    op.create_index("ix_patient_notes_primary_service_id", "patient_notes", ["primary_service_id"])
    op.create_index("ix_patient_notes_created_by_user_id", "patient_notes", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_patient_notes_created_by_user_id", table_name="patient_notes")
    op.drop_index("ix_patient_notes_primary_service_id", table_name="patient_notes")
    op.drop_index("ix_patient_notes_patient_id", table_name="patient_notes")
    op.drop_index("ix_patient_notes_organization_id", table_name="patient_notes")
    op.drop_table("patient_notes")

    op.drop_index(
        "ix_patient_service_enrollments_assigned_staff_user_id",
        table_name="patient_service_enrollments",
    )
    op.drop_index("ix_patient_service_enrollments_service_id", table_name="patient_service_enrollments")
    op.drop_index("ix_patient_service_enrollments_patient_id", table_name="patient_service_enrollments")
    op.drop_index(
        "ix_patient_service_enrollments_organization_id",
        table_name="patient_service_enrollments",
    )
    op.drop_table("patient_service_enrollments")

    op.drop_index("ix_services_organization_id", table_name="services")
    op.drop_table("services")
