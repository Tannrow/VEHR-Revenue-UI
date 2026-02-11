from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import (
    SUPPORTED_ROLE_KEYS,
    default_permissions_for_role,
    iter_default_role_definitions,
    normalize_role_key,
    role_label,
)
from app.db.models.organization_role import OrganizationRole
from app.db.models.organization_role_permission import OrganizationRolePermission


@dataclass(frozen=True)
class RoleRecord:
    key: str
    name: str
    is_system: bool
    permissions: tuple[str, ...]


def ensure_org_roles_seeded(db: Session, *, organization_id: str) -> None:
    existing_rows = db.execute(
        select(OrganizationRole).where(OrganizationRole.organization_id == organization_id)
    ).scalars().all()
    existing_by_key = {row.key: row for row in existing_rows}

    changed = False
    for definition in iter_default_role_definitions():
        role_row = existing_by_key.get(definition.key)
        if role_row is None:
            role_row = OrganizationRole(
                organization_id=organization_id,
                key=definition.key,
                name=definition.name,
                is_system=True,
            )
            db.add(role_row)
            db.flush()
            existing_by_key[definition.key] = role_row
            changed = True
        else:
            if role_row.is_system and role_row.name != definition.name:
                role_row.name = definition.name
                db.add(role_row)
                changed = True

        current_permissions = set(
            db.execute(
                select(OrganizationRolePermission.permission).where(
                    OrganizationRolePermission.organization_role_id == role_row.id
                )
            ).scalars().all()
        )
        if current_permissions:
            continue

        for permission in definition.permissions:
            db.add(
                OrganizationRolePermission(
                    organization_role_id=role_row.id,
                    permission=permission,
                )
            )
        changed = True

    if changed:
        db.commit()


def list_org_roles(db: Session, *, organization_id: str) -> list[RoleRecord]:
    ensure_org_roles_seeded(db, organization_id=organization_id)

    role_rows = db.execute(
        select(OrganizationRole)
        .where(OrganizationRole.organization_id == organization_id)
        .order_by(OrganizationRole.name.asc())
    ).scalars().all()

    permission_rows = db.execute(
        select(
            OrganizationRolePermission.organization_role_id,
            OrganizationRolePermission.permission,
        ).where(
            OrganizationRolePermission.organization_role_id.in_([row.id for row in role_rows])
        )
    ).all()
    permissions_by_role_id: dict[str, set[str]] = {}
    for role_id, permission in permission_rows:
        permissions_by_role_id.setdefault(role_id, set()).add(permission)

    return [
        RoleRecord(
            key=row.key,
            name=row.name,
            is_system=row.is_system,
            permissions=tuple(sorted(permissions_by_role_id.get(row.id, set()))),
        )
        for row in role_rows
    ]


def valid_role_keys_for_org(db: Session, *, organization_id: str) -> set[str]:
    roles = list_org_roles(db, organization_id=organization_id)
    return {item.key for item in roles}


def normalize_role_for_org(db: Session, *, organization_id: str, role: str) -> str:
    ensure_org_roles_seeded(db, organization_id=organization_id)
    normalized = normalize_role_key(role)
    role_keys = valid_role_keys_for_org(db, organization_id=organization_id)
    if normalized in role_keys:
        return normalized
    if normalized in SUPPORTED_ROLE_KEYS:
        return normalized
    raise ValueError("invalid_role")


def update_role_permissions(
    db: Session,
    *,
    organization_id: str,
    role_key: str,
    permissions: list[str],
) -> RoleRecord:
    ensure_org_roles_seeded(db, organization_id=organization_id)
    normalized_role_key = normalize_role_key(role_key)

    role_row = db.execute(
        select(OrganizationRole).where(
            OrganizationRole.organization_id == organization_id,
            OrganizationRole.key == normalized_role_key,
        )
    ).scalar_one_or_none()
    if role_row is None:
        raise ValueError("role_not_found")

    normalized_permissions = sorted({item.strip() for item in permissions if item.strip()})
    if not normalized_permissions:
        normalized_permissions = sorted(default_permissions_for_role(normalized_role_key))

    db.execute(
        OrganizationRolePermission.__table__.delete().where(
            OrganizationRolePermission.organization_role_id == role_row.id
        )
    )
    for permission in normalized_permissions:
        db.add(
            OrganizationRolePermission(
                organization_role_id=role_row.id,
                permission=permission,
            )
        )
    db.commit()

    return RoleRecord(
        key=role_row.key,
        name=role_row.name or role_label(role_row.key),
        is_system=role_row.is_system,
        permissions=tuple(normalized_permissions),
    )
