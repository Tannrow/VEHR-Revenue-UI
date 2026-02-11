from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, require_permission
from app.core.rbac import ROLE_ADMIN
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.session import get_db
from app.services.audit import log_event
from app.services.rbac_roles import ensure_org_roles_seeded


router = APIRouter(tags=["Organizations"])


class OrganizationCreate(BaseModel):
    name: str


class OrganizationRead(BaseModel):
    id: str
    name: str


@router.get("/organizations", response_model=list[OrganizationRead])
def list_organizations(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> list[OrganizationRead]:
    org_ids = (
        db.execute(
            select(OrganizationMembership.organization_id).where(
                OrganizationMembership.user_id == membership.user_id
            )
        )
        .scalars()
        .all()
    )
    organizations = (
        db.execute(select(Organization).where(Organization.id.in_(org_ids)))
        .scalars()
        .all()
    )
    return [OrganizationRead(id=org.id, name=org.name) for org in organizations]


@router.post("/organizations", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("org:manage")),
) -> OrganizationRead:
    organization = Organization(name=payload.name)
    db.add(organization)
    db.commit()
    db.refresh(organization)

    admin_membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=membership.user_id,
        role=ROLE_ADMIN,
    )
    db.add(admin_membership)
    db.commit()
    ensure_org_roles_seeded(db, organization_id=organization.id)

    log_event(
        db,
        action="create_organization",
        entity_type="organization",
        entity_id=organization.id,
        organization_id=organization.id,
        actor=membership.user.email,
    )

    return OrganizationRead(id=organization.id, name=organization.name)
