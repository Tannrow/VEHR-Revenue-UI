ROLE_ADMIN = "Administrator"
ROLE_COUNSELOR = "Counselor"
ROLE_CASE_MANAGER = "Case Manager"
ROLE_CLINICIAN = "Clinician"
ROLE_THERAPIST = "Therapist"
ROLE_MEDICAL_PROVIDER = "Medical Provider"
ROLE_STAFF = "Staff"
ROLE_BILLING = "Billing"
ROLE_COMPLIANCE = "Compliance Manager"
ROLE_CONSULTANT = "Consultant"
ROLE_MEDICAL_ASSISTANT = "Medical Assistant"

ROLE_PERMISSIONS: dict[str, set[str]] = {
    ROLE_ADMIN: {
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
    ROLE_COUNSELOR: {
        "patients:read",
        "patients:write",
        "patient:create",
        "encounters:read",
        "encounters:write",
        "encounter:create",
        "forms:read",
        "forms:write",
        "form_submission:create",
        "documents:read",
        "documents:write",
        "services:read",
    },
    ROLE_CASE_MANAGER: {
        "patients:read",
        "patients:write",
        "patient:create",
        "encounters:read",
        "encounters:write",
        "encounter:create",
        "forms:read",
        "forms:write",
        "form_submission:create",
        "documents:read",
        "documents:write",
        "services:read",
    },
    ROLE_COMPLIANCE: {
        "patients:read",
        "encounters:read",
        "forms:read",
        "documents:read",
        "audit:read",
        "clinical_audit:run",
        "clinical_audit:review",
        "services:read",
    },
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
    ROLE_BILLING: {
        "patients:read",
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

PERMISSION_ALIASES: dict[str, set[str]] = {
    "patient:create": {"patients:write"},
    "encounter:create": {"encounters:write"},
    "forms:manage": {"forms:write"},
    "form_submission:create": {"forms:write"},
    "patients:write": {"patient:create"},
    "encounters:write": {"encounter:create"},
    "forms:write": {"forms:manage", "form_submission:create"},
}


def is_valid_role(role: str) -> bool:
    return role in ROLE_PERMISSIONS


def has_permission(role: str, permission: str) -> bool:
    granted = ROLE_PERMISSIONS.get(role, set())
    if permission in granted:
        return True

    for alias in PERMISSION_ALIASES.get(permission, set()):
        if alias in granted:
            return True
    return False
