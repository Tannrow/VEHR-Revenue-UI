from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, require_permission
from app.db.models.organization_membership import OrganizationMembership
from app.db.session import get_db
from app.services.audit import log_event
from app.services.microsoft_graph import (
    MicrosoftGraphServiceError,
    get_sharepoint_item_download,
    list_sharepoint_children,
    list_sharepoint_drives,
    search_sharepoint_sites,
)


router = APIRouter(tags=["SharePoint"])


class SharePointSiteRead(BaseModel):
    id: str
    name: str
    web_url: str


class SharePointDriveRead(BaseModel):
    id: str
    name: str
    web_url: str


class SharePointItemRead(BaseModel):
    id: str
    name: str
    is_folder: bool
    size: int | None = None
    web_url: str
    last_modified_date_time: str | None = None
    mime_type: str | None = None


def _raise_graph_error(exc: MicrosoftGraphServiceError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail=exc.detail,
    ) from exc


@router.get("/sharepoint/sites", response_model=list[SharePointSiteRead])
def sharepoint_sites(
    search: str = Query(default=""),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("org:manage")),
) -> list[SharePointSiteRead]:
    try:
        rows = search_sharepoint_sites(
            db=db,
            organization_id=membership.organization_id,
            user_id=membership.user_id,
            search=search,
        )
    except MicrosoftGraphServiceError as exc:
        _raise_graph_error(exc)

    return [
        SharePointSiteRead(
            id=row.id,
            name=row.name,
            web_url=row.web_url,
        )
        for row in rows
    ]


@router.get("/sharepoint/sites/{site_id}/drives", response_model=list[SharePointDriveRead])
def sharepoint_site_drives(
    site_id: str,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("org:manage")),
) -> list[SharePointDriveRead]:
    try:
        rows = list_sharepoint_drives(
            db=db,
            organization_id=membership.organization_id,
            user_id=membership.user_id,
            site_id=site_id,
        )
    except MicrosoftGraphServiceError as exc:
        _raise_graph_error(exc)

    return [
        SharePointDriveRead(
            id=row.id,
            name=row.name,
            web_url=row.web_url,
        )
        for row in rows
    ]


@router.get("/sharepoint/drives/{drive_id}/root/children", response_model=list[SharePointItemRead])
def sharepoint_drive_root_children(
    drive_id: str,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("org:manage")),
) -> list[SharePointItemRead]:
    try:
        rows = list_sharepoint_children(
            db=db,
            organization_id=membership.organization_id,
            user_id=membership.user_id,
            drive_id=drive_id,
            item_id=None,
        )
    except MicrosoftGraphServiceError as exc:
        _raise_graph_error(exc)

    return [
        SharePointItemRead(
            id=row.id,
            name=row.name,
            is_folder=row.is_folder,
            size=row.size,
            web_url=row.web_url,
            last_modified_date_time=row.last_modified,
            mime_type=row.mime_type,
        )
        for row in rows
    ]


@router.get("/sharepoint/drives/{drive_id}/items/{item_id}/children", response_model=list[SharePointItemRead])
def sharepoint_drive_item_children(
    drive_id: str,
    item_id: str,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("org:manage")),
) -> list[SharePointItemRead]:
    try:
        rows = list_sharepoint_children(
            db=db,
            organization_id=membership.organization_id,
            user_id=membership.user_id,
            drive_id=drive_id,
            item_id=item_id,
        )
    except MicrosoftGraphServiceError as exc:
        _raise_graph_error(exc)

    return [
        SharePointItemRead(
            id=row.id,
            name=row.name,
            is_folder=row.is_folder,
            size=row.size,
            web_url=row.web_url,
            last_modified_date_time=row.last_modified,
            mime_type=row.mime_type,
        )
        for row in rows
    ]


@router.get("/sharepoint/drives/{drive_id}/items/{item_id}/download")
def sharepoint_drive_item_download(
    drive_id: str,
    item_id: str,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("org:manage")),
) -> StreamingResponse:
    try:
        payload = get_sharepoint_item_download(
            db=db,
            organization_id=membership.organization_id,
            user_id=membership.user_id,
            drive_id=drive_id,
            item_id=item_id,
        )
    except MicrosoftGraphServiceError as exc:
        _raise_graph_error(exc)

    log_event(
        db,
        action="sharepoint.download",
        entity_type="sharepoint_item",
        entity_id=item_id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={"drive_id": drive_id},
    )

    headers = {
        "Content-Disposition": f'inline; filename="{payload.filename}"',
        "Cache-Control": "no-store",
    }
    if payload.content_length is not None:
        headers["Content-Length"] = str(payload.content_length)
    if payload.web_url:
        headers["X-SharePoint-Web-Url"] = payload.web_url

    return StreamingResponse(
        payload.stream,
        media_type=payload.content_type or "application/octet-stream",
        headers=headers,
        status_code=status.HTTP_200_OK,
    )
