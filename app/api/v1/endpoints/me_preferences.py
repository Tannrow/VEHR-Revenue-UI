from __future__ import annotations

from typing import Final

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership
from app.core.rbac import (
    default_permissions_for_role,
    has_permission_for_organization,
    normalize_role_key,
    role_permissions_for_org,
)
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.user_preference import UserPreference
from app.db.session import get_db


router = APIRouter(tags=["Me Preferences"])

MODULE_IDS: Final[tuple[str, ...]] = (
    "care_delivery",
    "call_center",
    "workforce",
    "revenue_cycle",
    "governance",
    "administration",
)
MODULE_PERMISSION_ANY: Final[dict[str, tuple[str, ...]]] = {
    "care_delivery": (
        "clients:read",
        "forms:read",
        "documents:read",
        "tasks:read_self",
        "tasks:read_team",
        "tasks:read_all",
    ),
    "call_center": (
        "calls:read",
        "calls:write",
    ),
    "workforce": (
        "staff:read",
        "workforce:read",
        "workforce:approve_time",
    ),
    "revenue_cycle": (
        "billing:read",
        "billing:write",
    ),
    "governance": (
        "audit:read",
        "compliance:read",
        "clinical_audit:review",
    ),
    "administration": (
        "admin:org_settings",
        "admin:integrations",
        "users:manage",
        "tasks:read_all",
    ),
}


class MePreferencesRead(BaseModel):
    last_active_module: str | None = None
    sidebar_collapsed: bool
    copilot_enabled: bool
    allowed_modules: list[str]
    granted_permissions: list[str]


class MePreferencesPatch(BaseModel):
    last_active_module: str | None = None
    sidebar_collapsed: bool | None = None
    copilot_enabled: bool | None = None


def _get_or_create_preferences(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
) -> UserPreference:
    row = db.execute(
        select(UserPreference).where(
            UserPreference.organization_id == organization_id,
            UserPreference.user_id == user_id,
        )
    ).scalar_one_or_none()
    if row is not None:
        return row

    row = UserPreference(
        organization_id=organization_id,
        user_id=user_id,
        sidebar_collapsed=False,
        copilot_enabled=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _allowed_modules_for_membership(
    *,
    db: Session,
    membership: OrganizationMembership,
) -> list[str]:
    allowed: list[str] = []
    for module_id in MODULE_IDS:
        permissions = MODULE_PERMISSION_ANY.get(module_id, ())
        if not permissions:
            continue
        if any(
            has_permission_for_organization(
                db,
                organization_id=membership.organization_id,
                role=membership.role,
                permission=permission,
            )
            for permission in permissions
        ):
            allowed.append(module_id)
    return allowed


def _granted_permissions_for_membership(
    *,
    db: Session,
    membership: OrganizationMembership,
) -> list[str]:
    dynamic = role_permissions_for_org(
        db,
        organization_id=membership.organization_id,
        role=membership.role,
    )
    if dynamic is not None:
        return sorted(dynamic)

    fallback = default_permissions_for_role(normalize_role_key(membership.role))
    return sorted(fallback)


def _resolved_last_active_module(*, raw_module: str | None, allowed_modules: list[str]) -> str | None:
    if not raw_module:
        return None
    if raw_module in allowed_modules:
        return raw_module
    return None


@router.get("/me/preferences", response_model=MePreferencesRead)
def get_me_preferences(
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
) -> MePreferencesRead:
    row = _get_or_create_preferences(
        db=db,
        organization_id=membership.organization_id,
        user_id=membership.user_id,
    )
    allowed_modules = _allowed_modules_for_membership(db=db, membership=membership)
    return MePreferencesRead(
        last_active_module=_resolved_last_active_module(
            raw_module=row.last_active_module,
            allowed_modules=allowed_modules,
        ),
        sidebar_collapsed=row.sidebar_collapsed,
        copilot_enabled=row.copilot_enabled,
        allowed_modules=allowed_modules,
        granted_permissions=_granted_permissions_for_membership(db=db, membership=membership),
    )


@router.patch("/me/preferences", response_model=MePreferencesRead)
def patch_me_preferences(
    payload: MePreferencesPatch,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
) -> MePreferencesRead:
    row = _get_or_create_preferences(
        db=db,
        organization_id=membership.organization_id,
        user_id=membership.user_id,
    )
    allowed_modules = _allowed_modules_for_membership(db=db, membership=membership)

    if "last_active_module" in payload.model_fields_set:
        if payload.last_active_module is None:
            row.last_active_module = None
        else:
            candidate = payload.last_active_module.strip()
            if candidate not in MODULE_IDS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid module id",
                )
            if candidate not in allowed_modules:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Module access denied",
                )
            row.last_active_module = candidate

    if "sidebar_collapsed" in payload.model_fields_set and payload.sidebar_collapsed is not None:
        row.sidebar_collapsed = bool(payload.sidebar_collapsed)

    if "copilot_enabled" in payload.model_fields_set and payload.copilot_enabled is not None:
        row.copilot_enabled = bool(payload.copilot_enabled)

    db.add(row)
    db.commit()
    db.refresh(row)

    return MePreferencesRead(
        last_active_module=_resolved_last_active_module(
            raw_module=row.last_active_module,
            allowed_modules=allowed_modules,
        ),
        sidebar_collapsed=row.sidebar_collapsed,
        copilot_enabled=row.copilot_enabled,
        allowed_modules=allowed_modules,
        granted_permissions=_granted_permissions_for_membership(db=db, membership=membership),
    )
