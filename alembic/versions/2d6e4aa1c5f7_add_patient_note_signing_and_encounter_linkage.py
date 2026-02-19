"""add patient note signing and encounter linkage

Revision ID: 2d6e4aa1c5f7
Revises: 8b2d1f4a6c30
Create Date: 2026-02-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2d6e4aa1c5f7"
down_revision = "8b2d1f4a6c30"
branch_labels = None
depends_on = None


NOTE_STATUSES = ("draft", "signed")


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite" if bind is not None else False

    if is_sqlite:
        with op.batch_alter_table("patient_notes") as batch:
            batch.add_column(sa.Column("encounter_id", sa.String(length=36), nullable=True))
            batch.add_column(
                sa.Column(
                    "status",
                    sa.String(length=20),
                    nullable=False,
                    server_default=sa.text("'draft'"),
                )
            )
            batch.add_column(sa.Column("signed_by_user_id", sa.String(length=36), nullable=True))
            batch.add_column(sa.Column("signed_at", sa.DateTime(), nullable=True))

            batch.create_index("ix_patient_notes_encounter_id", ["encounter_id"])
            batch.create_index("ix_patient_notes_status", ["status"])
            batch.create_index("ix_patient_notes_signed_by_user_id", ["signed_by_user_id"])

            batch.create_check_constraint(
                "ck_patient_notes_status",
                f"status IN {NOTE_STATUSES}",
            )
            batch.create_check_constraint(
                "ck_patient_notes_signed_requires_encounter",
                "status != 'signed' OR encounter_id IS NOT NULL",
            )

            batch.alter_column("status", server_default=None)
    else:
        op.add_column(
            "patient_notes",
            sa.Column("encounter_id", sa.String(length=36), nullable=True),
        )
        op.add_column(
            "patient_notes",
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default=sa.text("'draft'"),
            ),
        )
        op.add_column(
            "patient_notes",
            sa.Column("signed_by_user_id", sa.String(length=36), nullable=True),
        )
        op.add_column(
            "patient_notes",
            sa.Column("signed_at", sa.DateTime(), nullable=True),
        )

        op.create_foreign_key(
            "fk_patient_notes_encounter_id_encounters",
            "patient_notes",
            "encounters",
            ["encounter_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_patient_notes_signed_by_user_id_users",
            "patient_notes",
            "users",
            ["signed_by_user_id"],
            ["id"],
        )

        op.create_index("ix_patient_notes_encounter_id", "patient_notes", ["encounter_id"])
        op.create_index("ix_patient_notes_status", "patient_notes", ["status"])
        op.create_index("ix_patient_notes_signed_by_user_id", "patient_notes", ["signed_by_user_id"])

        op.create_check_constraint(
            "ck_patient_notes_status",
            "patient_notes",
            f"status IN {NOTE_STATUSES}",
        )
        op.create_check_constraint(
            "ck_patient_notes_signed_requires_encounter",
            "patient_notes",
            "status != 'signed' OR encounter_id IS NOT NULL",
        )

        op.alter_column("patient_notes", "status", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_patient_notes_signed_requires_encounter", "patient_notes", type_="check")
    op.drop_constraint("ck_patient_notes_status", "patient_notes", type_="check")

    op.drop_index("ix_patient_notes_signed_by_user_id", table_name="patient_notes")
    op.drop_index("ix_patient_notes_status", table_name="patient_notes")
    op.drop_index("ix_patient_notes_encounter_id", table_name="patient_notes")

    op.drop_constraint(
        "fk_patient_notes_signed_by_user_id_users",
        "patient_notes",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_patient_notes_encounter_id_encounters",
        "patient_notes",
        type_="foreignkey",
    )

    op.drop_column("patient_notes", "signed_at")
    op.drop_column("patient_notes", "signed_by_user_id")
    op.drop_column("patient_notes", "status")
    op.drop_column("patient_notes", "encounter_id")
