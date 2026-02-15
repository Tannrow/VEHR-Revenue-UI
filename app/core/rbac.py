from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.organization_role import OrganizationRole
from app.db.models.organization_role_permission import OrganizationRolePermission

# Encompass 360 canonical roles
ROLE_ADMIN = "admin"
ROLE_OFFICE_MANAGER = "office_manager"
ROLE_COUNSELOR = "counselor"
ROLE_SUD_SUPERVISOR = "sud_supervisor"
ROLE_CASE_MANAGER = "case_manager"
ROLE_RECEPTIONIST = "receptionist"
ROLE_BILLING = "billing"
ROLE_COMPLIANCE = "compliance"
ROLE_FCS_STAFF = "fcs_staff"
ROLE_DRIVER = "driver"
ROLE_INTERN = "intern"

# Legacy compatibility role keys still referenced in older modules/tests.
ROLE_CLINICIAN = "clinician"
ROLE_THERAPIST = "therapist"
ROLE_MEDICAL_PROVIDER = "medical_provider"
ROLE_STAFF = "staff"
ROLE_CONSULTANT = "consultant"
ROLE_MEDICAL_ASSISTANT = "medical_assistant"

SUPPORTED_ROLE_KEYS: tuple[str, ...] = (
    ROLE_ADMIN,
    ROLE_OFFICE_MANAGER,
    ROLE_COUNSELOR,
    ROLE_SUD_SUPERVISOR,
    ROLE_CASE_MANAGER,
    ROLE_RECEPTIONIST,
    ROLE_BILLING,
    ROLE_COMPLIANCE,
    ROLE_FCS_STAFF,
    ROLE_DRIVER,
    ROLE_INTERN,
)

CORE_PERMISSIONS: tuple[str, ...] = (
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
    "analytics:view",
    "compliance:read",
    "compliance:write",
    "billing:read",
    "billing:write",
    "workforce:read",
    "workforce:approve_time",
)

ROLE_LABELS: dict[str, str] = {
    ROLE_ADMIN: "Admin",
    ROLE_OFFICE_MANAGER: "Office Manager",
    ROLE_COUNSELOR: "Counselor",
    ROLE_SUD_SUPERVISOR: "SUD Supervisor",
    ROLE_CASE_MANAGER: "Case Manager",
    ROLE_RECEPTIONIST: "Receptionist",
    ROLE_BILLING: "Billing",
    ROLE_COMPLIANCE: "Compliance",
    ROLE_FCS_STAFF: "FCS Staff",
    ROLE_DRIVER: "Driver",
    ROLE_INTERN: "Intern",
    ROLE_CLINICIAN: "Clinician",
    ROLE_THERAPIST: "Therapist",
    ROLE_MEDICAL_PROVIDER: "Medical Provider",
    ROLE_STAFF: "Staff",
    ROLE_CONSULTANT: "Consultant",
    ROLE_MEDICAL_ASSISTANT: "Medical Assistant",
}

DEFAULT_ROLE_PERMISSIONS: dict[str, set[str]] = {
    ROLE_ADMIN: {
        *CORE_PERMISSIONS,
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
        "analytics:view",
        "clinical_audit:run",
        "clinical_audit:review",
        "services:read",
        "services:write",
        "org:manage",
        "users:manage",
        "webhooks:manage",
    },
    ROLE_OFFICE_MANAGER: {
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
        "analytics:view",
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
    ROLE_COUNSELOR: {
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
    ROLE_SUD_SUPERVISOR: {
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
        "analytics:view",
        "compliance:read",
        "compliance:write",
        "documents:read",
        "documents:write",
        "forms:read",
        "forms:write",
        "services:read",
        "services:write",
    },
    ROLE_CASE_MANAGER: {
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
    ROLE_RECEPTIONIST: {
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
    ROLE_BILLING: {
        "tasks:read_self",
        "tasks:write_self",
        "tasks:read_team",
        "clients:read",
        "billing:read",
        "billing:write",
        "analytics:view",
        "documents:read",
        "services:read",
        "encounters:read",
    },
    ROLE_COMPLIANCE: {
        "tasks:read_self",
        "tasks:write_self",
        "tasks:read_team",
        "clients:read",
        "audits:read",
        "audits:write",
        "analytics:view",
        "compliance:read",
        "compliance:write",
        "documents:read",
        "audit:read",
        "clinical_audit:run",
        "clinical_audit:review",
    },
    ROLE_FCS_STAFF: {
        "tasks:read_self",
        "tasks:write_self",
        "leads:read",
        "clients:read",
        "calls:read",
        "documents:read",
        "services:read",
    },
    ROLE_DRIVER: {
        "tasks:read_self",
        "tasks:write_self",
        "clients:read",
        "calls:read",
        "workforce:read",
    },
    ROLE_INTERN: {
        "tasks:read_self",
        "leads:read",
        "clients:read",
        "documents:read",
    },
}

LEGACY_ROLE_PERMISSIONS: dict[str, set[str]] = {
    ROLE_CLINICIAN: {
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
        "clinical_audit:run",
        "services:read",
    },
    ROLE_THERAPIST: {
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
        "clinical_audit:run",
        "services:read",
    },
    ROLE_MEDICAL_PROVIDER: {
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
        "clinical_audit:run",
        "services:read",
    },
    ROLE_MEDICAL_ASSISTANT: {
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
        "clinical_audit:run",
        "services:read",
    },
    ROLE_STAFF: {
        "patients:read",
        "forms:read",
        "encounters:read",
        "documents:read",
        "services:read",
    },
    ROLE_CONSULTANT: {
        "patients:read",
        "encounters:read",
        "forms:read",
        "documents:read",
        "services:read",
    },
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    **DEFAULT_ROLE_PERMISSIONS,
    **LEGACY_ROLE_PERMISSIONS,
}

LEGACY_ROLE_ALIASES: dict[str, str] = {
    "Administrator": ROLE_ADMIN,
    "Counselor": ROLE_COUNSELOR,
    "Case Manager": ROLE_CASE_MANAGER,
    "Clinician": ROLE_CLINICIAN,
    "Therapist": ROLE_THERAPIST,
    "Medical Provider": ROLE_MEDICAL_PROVIDER,
    "Staff": ROLE_STAFF,
    "Billing": ROLE_BILLING,
    "Compliance Manager": ROLE_COMPLIANCE,
    "Consultant": ROLE_CONSULTANT,
    "Medical Assistant": ROLE_MEDICAL_ASSISTANT,
}

PERMISSION_ALIASES: dict[str, set[str]] = {
    "patient:create": {"patients:write", "clients:write"},
    "encounter:create": {"encounters:write"},
    "forms:manage": {"forms:write"},
    "form_submission:create": {"forms:write"},
    "patients:write": {"patient:create", "clients:write"},
    "patients:read": {"clients:read"},
    "clients:read": {"patients:read"},
    "clients:write": {"patients:write", "patient:create"},
    "encounters:write": {"encounter:create"},
    "forms:write": {"forms:manage", "form_submission:create"},
    "audits:read": {"audit:read"},
    "audit:read": {"audits:read"},
    "analytics:view": {"audit:read", "audits:read"},
    "admin:org_settings": {"org:manage"},
    "admin:integrations": {"org:manage"},
    "admin:role_permissions": {"users:manage", "org:manage"},
    "org:manage": {"admin:org_settings", "admin:integrations", "admin:role_permissions"},
    "users:manage": {"admin:role_permissions", "staff:manage"},
    "staff:manage": {"users:manage", "admin:role_permissions"},
    "staff:read": {"users:manage", "staff:manage"},
}


@dataclass(frozen=True)
class RoleDefinition:
    key: str
    name: str
    permissions: tuple[str, ...]


def normalize_role_key(role: str) -> str:
    candidate = (role or "").strip()
    if not candidate:
        return ""
    if candidate in ROLE_PERMISSIONS:
        return candidate

    alias = LEGACY_ROLE_ALIASES.get(candidate)
    if alias:
        return alias

    lowered = candidate.lower()
    if lowered in ROLE_PERMISSIONS:
        return lowered

    for legacy_name, mapped in LEGACY_ROLE_ALIASES.items():
        if legacy_name.lower() == lowered:
            return mapped

    return candidate


def role_label(role: str) -> str:
    normalized = normalize_role_key(role)
    return ROLE_LABELS.get(normalized) or normalized.replace("_", " ").title()


def permission_catalog() -> list[str]:
    return sorted(CORE_PERMISSIONS)


def iter_default_role_definitions() -> list[RoleDefinition]:
    return [
        RoleDefinition(
            key=role_key,
            name=ROLE_LABELS.get(role_key, role_key.replace("_", " ").title()),
            permissions=tuple(sorted(DEFAULT_ROLE_PERMISSIONS.get(role_key, set()))),
        )
        for role_key in SUPPORTED_ROLE_KEYS
    ]


def default_permissions_for_role(role: str) -> set[str]:
    normalized = normalize_role_key(role)
    return set(ROLE_PERMISSIONS.get(normalized, set()))


def is_valid_role(role: str) -> bool:
    normalized = normalize_role_key(role)
    return normalized in ROLE_PERMISSIONS


def _permission_granted(granted: Iterable[str], permission: str) -> bool:
    granted_set = set(granted)
    if permission in granted_set:
        return True
    for alias in PERMISSION_ALIASES.get(permission, set()):
        if alias in granted_set:
            return True
    return False


def has_permission(role: str, permission: str) -> bool:
    normalized = normalize_role_key(role)
    granted = ROLE_PERMISSIONS.get(normalized, set())
    return _permission_granted(granted, permission)


def role_permissions_for_org(
    db: Session,
    *,
    organization_id: str,
    role: str,
) -> set[str] | None:
    normalized = normalize_role_key(role)
    if not normalized:
        return None

    role_row = db.execute(
        select(OrganizationRole).where(
            OrganizationRole.organization_id == organization_id,
            OrganizationRole.key == normalized,
        )
    ).scalar_one_or_none()
    if role_row is None:
        return None

    rows = db.execute(
        select(OrganizationRolePermission.permission).where(
            OrganizationRolePermission.organization_role_id == role_row.id
        )
    ).scalars().all()
    return set(rows)


def has_permission_for_organization(
    db: Session,
    *,
    organization_id: str,
    role: str,
    permission: str,
) -> bool:
    dynamic_permissions = role_permissions_for_org(
        db,
        organization_id=organization_id,
        role=role,
    )
    if dynamic_permissions is not None:
        return _permission_granted(dynamic_permissions, permission)
    return has_permission(role, permission)
