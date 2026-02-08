"""add phase 2 paperwork, portal, and disclosure tables

Revision ID: f4d1a8c9b2e3
Revises: e7c4f1a2b3d4
Create Date: 2026-02-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f4d1a8c9b2e3"
down_revision = "e7c4f1a2b3d4"
branch_labels = None
depends_on = None


REQUIREMENT_TYPES = ("required", "optional")
TRIGGERS = ("on_enrollment", "annual")
PATIENT_DOCUMENT_STATUSES = ("required", "sent", "completed", "expired")


def upgrade() -> None:
    op.create_table(
        "service_document_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("service_id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("requirement_type", sa.String(length=20), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("validity_days", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f"requirement_type IN {REQUIREMENT_TYPES}",
            name="ck_service_document_templates_requirement_type",
        ),
        sa.CheckConstraint(
            f"trigger IN {TRIGGERS}",
            name="ck_service_document_templates_trigger",
        ),
        sa.CheckConstraint(
            "validity_days IS NULL OR validity_days > 0",
            name="ck_service_document_templates_validity_days",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["form_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "service_id",
            "template_id",
            "trigger",
            name="uq_service_document_templates_service_template_trigger",
        ),
    )
    op.create_index(
        "ix_service_document_templates_organization_id",
        "service_document_templates",
        ["organization_id"],
    )
    op.create_index(
        "ix_service_document_templates_service_id",
        "service_document_templates",
        ["service_id"],
    )
    op.create_index(
        "ix_service_document_templates_template_id",
        "service_document_templates",
        ["template_id"],
    )

    op.create_table(
        "patient_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("service_id", sa.String(length=36), nullable=False),
        sa.Column("enrollment_id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("service_document_template_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f"status IN {PATIENT_DOCUMENT_STATUSES}",
            name="ck_patient_documents_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
        sa.ForeignKeyConstraint(["enrollment_id"], ["patient_service_enrollments.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["form_templates.id"]),
        sa.ForeignKeyConstraint(
            ["service_document_template_id"],
            ["service_document_templates.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "enrollment_id",
            "template_id",
            name="uq_patient_documents_enrollment_template",
        ),
    )
    op.create_index(
        "ix_patient_documents_organization_id",
        "patient_documents",
        ["organization_id"],
    )
    op.create_index(
        "ix_patient_documents_patient_id",
        "patient_documents",
        ["patient_id"],
    )
    op.create_index(
        "ix_patient_documents_service_id",
        "patient_documents",
        ["service_id"],
    )
    op.create_index(
        "ix_patient_documents_enrollment_id",
        "patient_documents",
        ["enrollment_id"],
    )
    op.create_index(
        "ix_patient_documents_template_id",
        "patient_documents",
        ["template_id"],
    )
    op.create_index(
        "ix_patient_documents_service_document_template_id",
        "patient_documents",
        ["service_document_template_id"],
    )

    op.create_table(
        "portal_access_codes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("patient_document_id", sa.String(length=36), nullable=True),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["patient_document_id"], ["patient_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_portal_access_codes_organization_id",
        "portal_access_codes",
        ["organization_id"],
    )
    op.create_index(
        "ix_portal_access_codes_patient_id",
        "portal_access_codes",
        ["patient_id"],
    )
    op.create_index(
        "ix_portal_access_codes_patient_document_id",
        "portal_access_codes",
        ["patient_document_id"],
    )

    op.create_table(
        "disclosure_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("service_id", sa.String(length=36), nullable=False),
        sa.Column("generated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("export_type", sa.String(length=50), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("disclosed_note_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_disclosure_logs_organization_id",
        "disclosure_logs",
        ["organization_id"],
    )
    op.create_index(
        "ix_disclosure_logs_patient_id",
        "disclosure_logs",
        ["patient_id"],
    )
    op.create_index(
        "ix_disclosure_logs_service_id",
        "disclosure_logs",
        ["service_id"],
    )
    op.create_index(
        "ix_disclosure_logs_generated_by_user_id",
        "disclosure_logs",
        ["generated_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_disclosure_logs_generated_by_user_id", table_name="disclosure_logs")
    op.drop_index("ix_disclosure_logs_service_id", table_name="disclosure_logs")
    op.drop_index("ix_disclosure_logs_patient_id", table_name="disclosure_logs")
    op.drop_index("ix_disclosure_logs_organization_id", table_name="disclosure_logs")
    op.drop_table("disclosure_logs")

    op.drop_index("ix_portal_access_codes_patient_document_id", table_name="portal_access_codes")
    op.drop_index("ix_portal_access_codes_patient_id", table_name="portal_access_codes")
    op.drop_index("ix_portal_access_codes_organization_id", table_name="portal_access_codes")
    op.drop_table("portal_access_codes")

    op.drop_index(
        "ix_patient_documents_service_document_template_id",
        table_name="patient_documents",
    )
    op.drop_index("ix_patient_documents_template_id", table_name="patient_documents")
    op.drop_index("ix_patient_documents_enrollment_id", table_name="patient_documents")
    op.drop_index("ix_patient_documents_service_id", table_name="patient_documents")
    op.drop_index("ix_patient_documents_patient_id", table_name="patient_documents")
    op.drop_index("ix_patient_documents_organization_id", table_name="patient_documents")
    op.drop_table("patient_documents")

    op.drop_index("ix_service_document_templates_template_id", table_name="service_document_templates")
    op.drop_index("ix_service_document_templates_service_id", table_name="service_document_templates")
    op.drop_index(
        "ix_service_document_templates_organization_id",
        table_name="service_document_templates",
    )
    op.drop_table("service_document_templates")
