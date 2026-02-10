import json
import os
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.deps import get_current_membership
from app.db.models.organization_membership import OrganizationMembership


router = APIRouter(tags=["SharePoint"])

DEFAULT_SHAREPOINT_HOME_URL = (
    "https://valleyhealthandcounseling.sharepoint.com/sites/ValleyHealthHomePage"
)
ALLOWED_SHAREPOINT_HOST = "sharepoint.com"
DEFAULT_QUICK_LINKS = (
    ("Policies", "Organization policies and procedures"),
    ("Training", "Training resources and onboarding"),
    ("Templates", "Operational templates and examples"),
    ("Contracts", "Contract and vendor documents"),
    ("Forms", "Frequently used organizational forms"),
)


class SharePointHomeResponse(BaseModel):
    organization_id: str
    home_url: str


class SharePointQuickLink(BaseModel):
    label: str
    url: str
    description: str | None = None


class SharePointSettingsResponse(BaseModel):
    home_url: str
    quick_links: list[SharePointQuickLink]


def _is_allowed_sharepoint_host(hostname: str) -> bool:
    normalized = hostname.strip().lower().rstrip(".")
    return normalized.endswith(f".{ALLOWED_SHAREPOINT_HOST}")


def _validate_sharepoint_url(raw_url: str) -> str:
    candidate = raw_url.strip()
    parsed = urlparse(candidate)
    if parsed.scheme != "https":
        raise ValueError("SharePoint URL must use https")
    if not parsed.hostname:
        raise ValueError("SharePoint URL must include a hostname")
    if not _is_allowed_sharepoint_host(parsed.hostname):
        raise ValueError("SharePoint URL host must be a sharepoint.com domain")
    return candidate


def _resolve_sharepoint_home_url(*, organization_id: str) -> str:
    # Organization-level settings table does not currently exist; env/default only for now.
    configured = os.getenv("SHAREPOINT_HOME_URL", "").strip()
    candidate = configured or DEFAULT_SHAREPOINT_HOME_URL
    return _validate_sharepoint_url(candidate)


def _default_quick_links(*, home_url: str) -> list[SharePointQuickLink]:
    return [
        SharePointQuickLink(label=label, url=home_url, description=description)
        for label, description in DEFAULT_QUICK_LINKS
    ]


def _resolve_sharepoint_quick_links(*, home_url: str) -> list[SharePointQuickLink]:
    configured = os.getenv("SHAREPOINT_QUICK_LINKS_JSON", "").strip()
    if not configured:
        return _default_quick_links(home_url=home_url)

    try:
        parsed = json.loads(configured)
    except json.JSONDecodeError as exc:
        raise ValueError("SHAREPOINT_QUICK_LINKS_JSON must be valid JSON") from exc

    if not isinstance(parsed, list):
        raise ValueError("SHAREPOINT_QUICK_LINKS_JSON must be a JSON array")

    links: list[SharePointQuickLink] = []
    for index, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ValueError(f"Quick link at index {index} must be an object")

        label = str(item.get("label", "")).strip()
        url = str(item.get("url", "")).strip()
        description_raw = item.get("description")
        description = None
        if description_raw is not None:
            description = str(description_raw).strip() or None

        if not label:
            raise ValueError(f"Quick link at index {index} is missing label")
        if not url:
            raise ValueError(f"Quick link at index {index} is missing url")

        links.append(
            SharePointQuickLink(
                label=label,
                url=_validate_sharepoint_url(url),
                description=description,
            )
        )

    if not links:
        return _default_quick_links(home_url=home_url)
    return links


@router.get("/sharepoint/home", response_model=SharePointHomeResponse)
def sharepoint_home(
    membership: OrganizationMembership = Depends(get_current_membership),
) -> SharePointHomeResponse:
    try:
        home_url = _resolve_sharepoint_home_url(organization_id=membership.organization_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid SharePoint configuration: {exc}",
        )

    return SharePointHomeResponse(
        organization_id=membership.organization_id,
        home_url=home_url,
    )


@router.get("/org/sharepoint-settings", response_model=SharePointSettingsResponse)
def sharepoint_settings(
    membership: OrganizationMembership = Depends(get_current_membership),
) -> SharePointSettingsResponse:
    try:
        home_url = _resolve_sharepoint_home_url(organization_id=membership.organization_id)
        quick_links = _resolve_sharepoint_quick_links(home_url=home_url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid SharePoint configuration: {exc}",
        )

    return SharePointSettingsResponse(
        home_url=home_url,
        quick_links=quick_links,
    )
