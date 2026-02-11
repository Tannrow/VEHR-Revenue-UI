from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, require_permission
from app.core.rbac import normalize_role_key, role_label
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.user import User
from app.db.session import get_db
from app.services.teams import TEAM_LABELS, team_key_for_role


router = APIRouter(tags=["Staff"])

TEAM_ORDER: tuple[str, ...] = tuple(
    name
    for name in (
        "admissions",
        "clinical",
        "billing",
        "compliance",
        "reception",
        "workforce",
    )
)


class TeamMemberRead(BaseModel):
    id: str
    full_name: str | None = None
    email: str
    role: str
    role_label: str


class TeamRead(BaseModel):
    name: str
    members: list[TeamMemberRead]


@router.get("/staff/teams", response_model=list[TeamRead])
def list_staff_teams(
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("staff:read")),
) -> list[TeamRead]:
    rows = db.execute(
        select(OrganizationMembership, User).where(
            OrganizationMembership.organization_id == membership.organization_id,
            OrganizationMembership.user_id == User.id,
        )
    ).all()

    teams: dict[str, list[TeamMemberRead]] = {team_key: [] for team_key in TEAM_ORDER}
    for membership_row, user_row in rows:
        normalized_role = normalize_role_key(membership_row.role)
        team_key = team_key_for_role(normalized_role)
        teams.setdefault(team_key, [])
        teams[team_key].append(
            TeamMemberRead(
                id=user_row.id,
                full_name=user_row.full_name,
                email=user_row.email,
                role=normalized_role,
                role_label=role_label(normalized_role),
            )
        )

    return [
        TeamRead(name=TEAM_LABELS.get(team_key, team_key.title()), members=teams.get(team_key, []))
        for team_key in TEAM_ORDER
    ]
