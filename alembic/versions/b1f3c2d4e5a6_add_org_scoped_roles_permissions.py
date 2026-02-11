"""add org scoped roles and permissions

Revision ID: b1f3c2d4e5a6
Revises: 6a9e8d3f2b41
Create Date: 2026-02-11 00:00:00.000000
"""

from datetime import datetime
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b1f3c2d4e5a6"
down_revision = "6a9e8d3f2b41"
branch_labels = None
depends_on = None


DEFAULT_ROLE_DEFINITIONS: dict[str, dict[str, object]] = {
    "admin": {
        "name": "Admin",
        "permissions": {
            "tasks:read_self",
            "tasks:write_self",
            "tasks:read_team",
            "tasks:read_all",
            "tasks:assign",
            "leads:read",
            "leads:write",
            "clients:read",
            "clients:write",
            "calls:read",
            "calls:write",
            "staff:read",
            "staff:manage",
            "admin:org_settings",
            "admin:role_permissions",
            "admin:integrations",
            "audits:read",
            "audits:write",
            "compliance:read",
            "compliance:write",
            "billing:read",
            "billing:write",
            "workforce:read",
            "workforce:approve_time",
            "patients:read",
            "patients:write",
            "patient:create",
            "encounters:read",
            "encounters:write",
            "encounter:create",
            "forms:read",
            "forms:write",
            "forms:manage",
            "form_submission:create",
            "documents:read",
            "documents:write",
            "audit:read",
            "clinical_audit:run",
            "clinical_audit:review",
            "services:read",
            "services:write",
            "org:manage",
            "users:manage",
            "webhooks:manage",
        },
    },
    "office_manager": {
        "name": "Office Manager",
        "permissions": {
            "tasks:read_self",
            "tasks:write_self",
            "tasks:read_team",
            "tasks:read_all",
            "tasks:assign",
            "leads:read",
            "leads:write",
            "clients:read",
            "clients:write",
            "calls:read",
            "calls:write",
            "staff:read",
            "staff:manage",
            "admin:org_settings",
            "admin:integrations",
            "audits:read",
            "audits:write",
            "compliance:read",
            "compliance:write",
            "billing:read",
            "billing:write",
            "workforce:read",
            "workforce:approve_time",
            "documents:read",
            "documents:write",
            "services:read",
            "services:write",
        },
    },
    "counselor": {
        "name": "Counselor",
        "permissions": {
            "tasks:read_self",
            "tasks:write_self",
            "tasks:read_team",
            "leads:read",
            "clients:read",
            "clients:write",
            "calls:read",
            "calls:write",
            "documents:read",
            "documents:write",
            "forms:read",
            "forms:write",
            "form_submission:create",
            "services:read",
        },
    },
    "sud_supervisor": {
        "name": "SUD Supervisor",
        "permissions": {
            "tasks:read_self",
            "tasks:write_self",
            "tasks:read_team",
            "tasks:read_all",
            "tasks:assign",
            "leads:read",
            "leads:write",
            "clients:read",
            "clients:write",
            "calls:read",
            "calls:write",
            "staff:read",
            "audits:read",
            "audits:write",
            "compliance:read",
            "compliance:write",
            "documents:read",
            "documents:write",
            "forms:read",
            "forms:write",
            "services:read",
            "services:write",
        },
    },
    "case_manager": {
        "name": "Case Manager",
        "permissions": {
            "tasks:read_self",
            "tasks:write_self",
            "tasks:read_team",
            "leads:read",
            "leads:write",
            "clients:read",
            "clients:write",
            "calls:read",
            "calls:write",
            "documents:read",
            "documents:write",
            "forms:read",
            "forms:write",
            "services:read",
        },
    },
    "receptionist": {
        "name": "Receptionist",
        "permissions": {
            "tasks:read_self",
            "tasks:write_self",
            "leads:read",
            "leads:write",
            "clients:read",
            "calls:read",
            "calls:write",
            "staff:read",
            "documents:read",
        },
    },
    "billing": {
        "name": "Billing",
        "permissions": {
            "tasks:read_self",
            "tasks:write_self",
            "tasks:read_team",
            "clients:read",
            "billing:read",
            "billing:write",
            "documents:read",
            "services:read",
            "encounters:read",
        },
    },
    "compliance": {
        "name": "Compliance",
        "permissions": {
            "tasks:read_self",
            "tasks:write_self",
            "tasks:read_team",
            "clients:read",
            "audits:read",
            "audits:write",
            "compliance:read",
            "compliance:write",
            "documents:read",
            "audit:read",
            "clinical_audit:run",
            "clinical_audit:review",
        },
    },
    "fcs_staff": {
        "name": "FCS Staff",
        "permissions": {
            "tasks:read_self",
            "tasks:write_self",
            "leads:read",
            "clients:read",
            "calls:read",
            "documents:read",
            "services:read",
        },
    },
    "driver": {
        "name": "Driver",
        "permissions": {
            "tasks:read_self",
            "tasks:write_self",
            "clients:read",
            "calls:read",
            "workforce:read",
        },
    },
    "intern": {
        "name": "Intern",
        "permissions": {
            "tasks:read_self",
            "leads:read",
            "clients:read",
            "documents:read",
        },
    },
}


def _seed_default_org_roles() -> None:
    bind = op.get_bind()
    org_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM organizations")).fetchall()]
    if not org_ids:
        return

    now = datetime.utcnow()
    role_table = sa.table(
        "organization_roles",
        sa.column("id", sa.String(length=36)),
        sa.column("organization_id", sa.String(length=36)),
        sa.column("key", sa.String(length=64)),
        sa.column("name", sa.String(length=120)),
        sa.column("is_system", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    permission_table = sa.table(
        "organization_role_permissions",
        sa.column("id", sa.String(length=36)),
        sa.column("organization_role_id", sa.String(length=36)),
        sa.column("permission", sa.String(length=120)),
        sa.column("created_at", sa.DateTime()),
    )

    role_rows: list[dict[str, object]] = []
    permission_rows: list[dict[str, object]] = []

    for organization_id in org_ids:
        for role_key, role_definition in DEFAULT_ROLE_DEFINITIONS.items():
            role_id = str(uuid4())
            role_rows.append(
                {
                    "id": role_id,
                    "organization_id": organization_id,
                    "key": role_key,
                    "name": role_definition["name"],
                    "is_system": True,
                    "created_at": now,
                    "updated_at": now,
                }
            )

            for permission in sorted(role_definition["permissions"]):
                permission_rows.append(
                    {
                        "id": str(uuid4()),
                        "organization_role_id": role_id,
                        "permission": permission,
                        "created_at": now,
                    }
                )

    if role_rows:
        op.bulk_insert(role_table, role_rows)
    if permission_rows:
        op.bulk_insert(permission_table, permission_rows)


def upgrade() -> None:
    op.create_table(
        "organization_roles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "key", name="uq_organization_roles_org_key"),
    )
    op.create_index("ix_organization_roles_organization_id", "organization_roles", ["organization_id"])
    op.create_index("ix_organization_roles_key", "organization_roles", ["key"])

    op.create_table(
        "organization_role_permissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_role_id", sa.String(length=36), nullable=False),
        sa.Column("permission", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["organization_role_id"], ["organization_roles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_role_id",
            "permission",
            name="uq_organization_role_permissions_role_permission",
        ),
    )
    op.create_index(
        "ix_organization_role_permissions_organization_role_id",
        "organization_role_permissions",
        ["organization_role_id"],
    )
    op.create_index(
        "ix_organization_role_permissions_permission",
        "organization_role_permissions",
        ["permission"],
    )

    _seed_default_org_roles()


def downgrade() -> None:
    op.drop_index("ix_organization_role_permissions_permission", table_name="organization_role_permissions")
    op.drop_index(
        "ix_organization_role_permissions_organization_role_id",
        table_name="organization_role_permissions",
    )
    op.drop_table("organization_role_permissions")

    op.drop_index("ix_organization_roles_key", table_name="organization_roles")
    op.drop_index("ix_organization_roles_organization_id", table_name="organization_roles")
    op.drop_table("organization_roles")
