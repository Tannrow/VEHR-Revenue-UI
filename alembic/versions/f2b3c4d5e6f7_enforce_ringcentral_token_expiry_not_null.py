"""enforce non-null token_expires_at on ringcentral_credentials

Revision ID: f2b3c4d5e6f7
Revises: e1f2d3c4b5a6
Create Date: 2026-02-12 12:00:00.000000
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f2b3c4d5e6f7"
down_revision = "e1f2d3c4b5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    fallback_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    bind.execute(
        sa.text(
            "UPDATE ringcentral_credentials "
            "SET token_expires_at = :fallback_expiry "
            "WHERE token_expires_at IS NULL"
        ),
        {"fallback_expiry": fallback_expiry},
    )

    with op.batch_alter_table("ringcentral_credentials") as batch_op:
        batch_op.alter_column(
            "token_expires_at",
            existing_type=sa.DateTime(),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("ringcentral_credentials") as batch_op:
        batch_op.alter_column(
            "token_expires_at",
            existing_type=sa.DateTime(),
            nullable=True,
        )
