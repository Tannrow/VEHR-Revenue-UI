from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.deps import get_current_membership, require_permission
from app.db.models.integration_account import IntegrationAccount
from app.db.models.integration_token import IntegrationToken
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.session import get_db
from app.services.audit import log_event


router = APIRouter(tags=["Admin Center"])


class OrganizationSettingsRead(BaseModel):
    organization_id: str
    name: str


class OrganizationSettingsUpdate(BaseModel):
    name: str


class IntegrationStatusItemRead(BaseModel):
    provider: str
    connected_accounts: int


class IntegrationStatusRead(BaseModel):
    organization_id: str
    items: list[IntegrationStatusItemRead]


@router.get("/admin/organization/settings", response_model=OrganizationSettingsRead)
def get_organization_settings(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("admin:org_settings")),
) -> OrganizationSettingsRead:
    organization = db.get(Organization, membership.organization_id)
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return OrganizationSettingsRead(
        organization_id=organization.id,
        name=organization.name,
    )


@router.patch("/admin/organization/settings", response_model=OrganizationSettingsRead)
def update_organization_settings(
    payload: OrganizationSettingsUpdate,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("admin:org_settings")),
) -> OrganizationSettingsRead:
    organization = db.get(Organization, membership.organization_id)
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    next_name = payload.name.strip()
    if not next_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization name cannot be empty")

    organization.name = next_name
    db.add(organization)
    db.commit()
    db.refresh(organization)

    log_event(
        db,
        action="organization.settings_updated",
        entity_type="organization",
        entity_id=organization.id,
        organization_id=organization.id,
        actor=membership.user.email,
        metadata={"name": organization.name},
    )

    return OrganizationSettingsRead(
        organization_id=organization.id,
        name=organization.name,
    )


@router.get("/admin/integrations/status", response_model=IntegrationStatusRead)
def integration_status(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("admin:integrations")),
) -> IntegrationStatusRead:
    account_rows = db.execute(
        select(
            IntegrationAccount.provider,
            func.count(IntegrationAccount.id),
        )
        .where(
            IntegrationAccount.organization_id == membership.organization_id,
            IntegrationAccount.revoked_at.is_(None),
        )
        .group_by(IntegrationAccount.provider)
        .order_by(IntegrationAccount.provider.asc())
    ).all()

    token_rows = db.execute(
        select(
            IntegrationToken.provider,
            func.count(IntegrationToken.id),
        )
        .where(IntegrationToken.organization_id == membership.organization_id)
        .group_by(IntegrationToken.provider)
        .order_by(IntegrationToken.provider.asc())
    ).all()

    counts_by_provider: dict[str, int] = {}
    for provider, count in account_rows:
        counts_by_provider[provider] = counts_by_provider.get(provider, 0) + int(count)
    for provider, count in token_rows:
        counts_by_provider[provider] = counts_by_provider.get(provider, 0) + int(count)

    items = [
        IntegrationStatusItemRead(provider=provider, connected_accounts=counts_by_provider[provider])
        for provider in sorted(counts_by_provider)
    ]
    return IntegrationStatusRead(
        organization_id=membership.organization_id,
        items=items,
    )
