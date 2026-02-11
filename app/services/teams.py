from app.core.rbac import normalize_role_key

TEAM_ADMISSIONS = "admissions"
TEAM_CLINICAL = "clinical"
TEAM_BILLING = "billing"
TEAM_COMPLIANCE = "compliance"
TEAM_RECEPTION = "reception"
TEAM_WORKFORCE = "workforce"
TEAM_UNASSIGNED = "unassigned"

TEAM_LABELS: dict[str, str] = {
    TEAM_ADMISSIONS: "Admissions team",
    TEAM_CLINICAL: "Clinical team",
    TEAM_BILLING: "Billing",
    TEAM_COMPLIANCE: "Compliance",
    TEAM_RECEPTION: "Reception",
    TEAM_WORKFORCE: "Workforce",
    TEAM_UNASSIGNED: "Unassigned",
}

ROLE_TO_TEAM: dict[str, str] = {
    "admin": TEAM_ADMISSIONS,
    "office_manager": TEAM_ADMISSIONS,
    "receptionist": TEAM_RECEPTION,
    "counselor": TEAM_CLINICAL,
    "sud_supervisor": TEAM_CLINICAL,
    "case_manager": TEAM_CLINICAL,
    "fcs_staff": TEAM_CLINICAL,
    "intern": TEAM_CLINICAL,
    "clinician": TEAM_CLINICAL,
    "therapist": TEAM_CLINICAL,
    "medical_provider": TEAM_CLINICAL,
    "medical_assistant": TEAM_CLINICAL,
    "staff": TEAM_CLINICAL,
    "consultant": TEAM_CLINICAL,
    "billing": TEAM_BILLING,
    "compliance": TEAM_COMPLIANCE,
    "driver": TEAM_WORKFORCE,
}


def team_key_for_role(role: str) -> str:
    normalized = normalize_role_key(role)
    return ROLE_TO_TEAM.get(normalized, TEAM_UNASSIGNED)


def team_label(team_key: str) -> str:
    return TEAM_LABELS.get(team_key, team_key.replace("_", " ").title())
