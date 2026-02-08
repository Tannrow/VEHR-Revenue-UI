import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, get_current_organization, require_permission
from app.core.rbac import (
    ROLE_ADMIN,
    ROLE_CLINICIAN,
    ROLE_MEDICAL_ASSISTANT,
    ROLE_MEDICAL_PROVIDER,
    ROLE_STAFF,
    ROLE_THERAPIST,
    has_permission,
)
from app.core.time import utc_now
from app.db.models.announcement import Announcement
from app.db.models.encounter import Encounter
from app.db.models.organization_tile import OrganizationTile
from app.db.models.patient_document import PatientDocument
from app.db.models.patient_service_enrollment import PatientServiceEnrollment
from app.db.session import get_db
from app.services.audit import log_event


router = APIRouter(tags=["Organization"])

LINK_TYPES = {"internal_route", "external_url"}
CLINICAL_OR_SUPERVISORY_ROLES = {
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_CLINICIAN,
    ROLE_THERAPIST,
    ROLE_MEDICAL_PROVIDER,
    ROLE_MEDICAL_ASSISTANT,
}


class OrganizationTileBase(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    icon: str = Field(min_length=1, max_length=60)
    category: str = Field(min_length=1, max_length=50)
    link_type: str
    href: str = Field(min_length=1, max_length=500)
    sort_order: int = 0
    required_permissions: list[str] = Field(default_factory=list)
    is_active: bool = True


class OrganizationTileCreate(OrganizationTileBase):
    pass


class OrganizationTileUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    icon: str | None = Field(default=None, min_length=1, max_length=60)
    category: str | None = Field(default=None, min_length=1, max_length=50)
    link_type: str | None = None
    href: str | None = Field(default=None, min_length=1, max_length=500)
    sort_order: int | None = None
    required_permissions: list[str] | None = None
    is_active: bool | None = None


class TileReorderRequest(BaseModel):
    ordered_ids: list[str]


class OrganizationTileRead(BaseModel):
    id: str
    title: str
    icon: str
    category: str
    link_type: str
    href: str
    sort_order: int
    required_permissions: list[str]
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    start_date: date
    end_date: date | None = None
    is_active: bool = True


class AnnouncementUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1)
    start_date: date | None = None
    end_date: date | None = None
    is_active: bool | None = None


class AnnouncementRead(BaseModel):
    id: str
    title: str
    body: str
    start_date: date
    end_date: date | None = None
    is_active: bool
    created_at: str


class OrganizationHomeResponse(BaseModel):
    tiles: list[OrganizationTileRead]
    announcements: list[AnnouncementRead]


class WorkSummaryItem(BaseModel):
    key: str
    title: str
    count: int
    href: str


class WorkSummaryResponse(BaseModel):
    show_widget: bool
    items: list[WorkSummaryItem]


def _normalize_link_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in LINK_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid link_type. Expected one of: {', '.join(sorted(LINK_TYPES))}",
        )
    return normalized


def _normalize_permissions(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        trimmed = value.strip()
        if not trimmed:
            continue
        if trimmed not in normalized:
            normalized.append(trimmed)
    return normalized


def _permissions_json(values: list[str]) -> str:
    return json.dumps(_normalize_permissions(values))


def _permissions_from_json(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if isinstance(item, str)]


def _tile_read(row: OrganizationTile) -> OrganizationTileRead:
    return OrganizationTileRead(
        id=row.id,
        title=row.title,
        icon=row.icon,
        category=row.category,
        link_type=row.link_type,
        href=row.href,
        sort_order=row.sort_order,
        required_permissions=_permissions_from_json(row.required_permissions_json),
        is_active=row.is_active,
    )


def _announcement_read(row: Announcement) -> AnnouncementRead:
    return AnnouncementRead(
        id=row.id,
        title=row.title,
        body=row.body,
        start_date=row.start_date,
        end_date=row.end_date,
        is_active=row.is_active,
        created_at=row.created_at.isoformat(),
    )


def _default_tile_specs() -> list[dict]:
    return [
        {
            "title": "SUD",
            "icon": "beaker",
            "category": "Clinical Ops",
            "link_type": "internal_route",
            "href": "/patients",
            "sort_order": 10,
            "required_permissions": ["patients:read"],
        },
        {
            "title": "Case Management",
            "icon": "briefcase",
            "category": "Clinical Ops",
            "link_type": "internal_route",
            "href": "/patients",
            "sort_order": 20,
            "required_permissions": ["patients:read"],
        },
        {
            "title": "Forms",
            "icon": "file-text",
            "category": "Clinical Ops",
            "link_type": "internal_route",
            "href": "/forms-builder",
            "sort_order": 30,
            "required_permissions": ["forms:read"],
        },
        {
            "title": "Templates",
            "icon": "layers",
            "category": "Clinical Ops",
            "link_type": "internal_route",
            "href": "/forms/templates",
            "sort_order": 40,
            "required_permissions": ["forms:read"],
        },
        {
            "title": "Compliance",
            "icon": "shield-check",
            "category": "Compliance",
            "link_type": "internal_route",
            "href": "/audit-center",
            "sort_order": 50,
            "required_permissions": ["audit:read"],
        },
        {
            "title": "Policy",
            "icon": "book-open",
            "category": "Compliance",
            "link_type": "external_url",
            "href": "https://sharepoint.com",
            "sort_order": 60,
            "required_permissions": ["audit:read"],
        },
        {
            "title": "Grievances",
            "icon": "alert-triangle",
            "category": "Compliance",
            "link_type": "internal_route",
            "href": "/organization/home?panel=grievances",
            "sort_order": 70,
            "required_permissions": ["audit:read"],
        },
        {
            "title": "Licenses",
            "icon": "badge-check",
            "category": "Compliance",
            "link_type": "internal_route",
            "href": "/organization/home?panel=licenses",
            "sort_order": 80,
            "required_permissions": ["audit:read"],
        },
        {
            "title": "Supervisors",
            "icon": "users",
            "category": "Staff/Ops",
            "link_type": "internal_route",
            "href": "/organization/home?panel=supervisors",
            "sort_order": 90,
            "required_permissions": ["patients:read"],
        },
        {
            "title": "Training",
            "icon": "graduation-cap",
            "category": "Staff/Ops",
            "link_type": "internal_route",
            "href": "/organization/home?panel=training",
            "sort_order": 100,
            "required_permissions": ["patients:read"],
        },
        {
            "title": "Call Log",
            "icon": "phone-call",
            "category": "Staff/Ops",
            "link_type": "internal_route",
            "href": "/organization/home?panel=call-log",
            "sort_order": 110,
            "required_permissions": ["patients:read"],
        },
        {
            "title": "Contracts",
            "icon": "file-signature",
            "category": "Staff/Ops",
            "link_type": "internal_route",
            "href": "/organization/home?panel=contracts",
            "sort_order": 120,
            "required_permissions": ["patients:read"],
        },
    ]


def _ensure_default_tiles(
    db: Session,
    *,
    organization_id: str,
    created_by_user_id: str | None,
) -> None:
    existing = db.execute(
        select(OrganizationTile.id).where(OrganizationTile.organization_id == organization_id)
    ).first()
    if existing:
        return

    for spec in _default_tile_specs():
        db.add(
            OrganizationTile(
                organization_id=organization_id,
                title=spec["title"],
                icon=spec["icon"],
                category=spec["category"],
                link_type=spec["link_type"],
                href=spec["href"],
                sort_order=spec["sort_order"],
                required_permissions_json=_permissions_json(spec["required_permissions"]),
                is_active=True,
                created_by_user_id=created_by_user_id,
            )
        )
    db.commit()


def _user_can_view_tile(row: OrganizationTile, *, role: str) -> bool:
    required_permissions = _permissions_from_json(row.required_permissions_json)
    if not required_permissions:
        return True
    return all(has_permission(role, permission) for permission in required_permissions)


def _today_date() -> date:
    return utc_now().date()


@router.get("/organization/home", response_model=OrganizationHomeResponse)
def organization_home(
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
) -> OrganizationHomeResponse:
    _ensure_default_tiles(
        db,
        organization_id=organization.id,
        created_by_user_id=membership.user_id,
    )

    tiles = db.execute(
        select(OrganizationTile)
        .where(
            OrganizationTile.organization_id == organization.id,
            OrganizationTile.is_active.is_(True),
        )
        .order_by(OrganizationTile.sort_order.asc(), OrganizationTile.title.asc())
    ).scalars().all()
    visible_tiles = [
        _tile_read(row)
        for row in tiles
        if _user_can_view_tile(row, role=membership.role)
    ]

    today = _today_date()
    announcements = db.execute(
        select(Announcement)
        .where(
            Announcement.organization_id == organization.id,
            Announcement.is_active.is_(True),
            Announcement.start_date <= today,
            (Announcement.end_date.is_(None) | (Announcement.end_date >= today)),
        )
        .order_by(Announcement.start_date.desc(), Announcement.created_at.desc())
    ).scalars().all()
    return OrganizationHomeResponse(
        tiles=visible_tiles,
        announcements=[_announcement_read(row) for row in announcements],
    )


@router.get("/organization/tiles", response_model=list[OrganizationTileRead])
def list_organization_tiles(
    include_inactive: bool = Query(False),
    for_settings: bool = Query(False),
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
) -> list[OrganizationTileRead]:
    _ensure_default_tiles(
        db,
        organization_id=organization.id,
        created_by_user_id=membership.user_id,
    )

    if for_settings and not has_permission(membership.role, "org:manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    query = select(OrganizationTile).where(OrganizationTile.organization_id == organization.id)
    if not include_inactive:
        query = query.where(OrganizationTile.is_active.is_(True))
    rows = db.execute(
        query.order_by(OrganizationTile.sort_order.asc(), OrganizationTile.title.asc())
    ).scalars().all()

    if for_settings:
        return [_tile_read(row) for row in rows]
    return [_tile_read(row) for row in rows if _user_can_view_tile(row, role=membership.role)]


@router.post("/organization/tiles", response_model=OrganizationTileRead, status_code=status.HTTP_201_CREATED)
def create_organization_tile(
    payload: OrganizationTileCreate,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("org:manage")),
) -> OrganizationTileRead:
    link_type = _normalize_link_type(payload.link_type)
    row = OrganizationTile(
        organization_id=organization.id,
        title=payload.title.strip(),
        icon=payload.icon.strip(),
        category=payload.category.strip(),
        link_type=link_type,
        href=payload.href.strip(),
        sort_order=payload.sort_order,
        required_permissions_json=_permissions_json(payload.required_permissions),
        is_active=payload.is_active,
        created_by_user_id=membership.user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    log_event(
        db,
        action="tile.created",
        entity_type="organization_tile",
        entity_id=row.id,
        organization_id=organization.id,
        actor=membership.user.email,
    )
    return _tile_read(row)


@router.patch("/organization/tiles/{tile_id}", response_model=OrganizationTileRead)
def update_organization_tile(
    tile_id: str,
    payload: OrganizationTileUpdate,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("org:manage")),
) -> OrganizationTileRead:
    row = db.execute(
        select(OrganizationTile).where(
            OrganizationTile.id == tile_id,
            OrganizationTile.organization_id == organization.id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tile not found")

    if payload.title is not None:
        row.title = payload.title.strip()
    if payload.icon is not None:
        row.icon = payload.icon.strip()
    if payload.category is not None:
        row.category = payload.category.strip()
    if payload.link_type is not None:
        row.link_type = _normalize_link_type(payload.link_type)
    if payload.href is not None:
        row.href = payload.href.strip()
    if payload.sort_order is not None:
        row.sort_order = payload.sort_order
    if payload.required_permissions is not None:
        row.required_permissions_json = _permissions_json(payload.required_permissions)
    if payload.is_active is not None:
        row.is_active = payload.is_active

    db.add(row)
    db.commit()
    db.refresh(row)

    log_event(
        db,
        action="tile.updated",
        entity_type="organization_tile",
        entity_id=row.id,
        organization_id=organization.id,
        actor=membership.user.email,
    )
    return _tile_read(row)


@router.post("/organization/tiles/reorder", response_model=list[OrganizationTileRead])
def reorder_organization_tiles(
    payload: TileReorderRequest,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    _: None = Depends(require_permission("org:manage")),
) -> list[OrganizationTileRead]:
    rows = db.execute(
        select(OrganizationTile).where(OrganizationTile.organization_id == organization.id)
    ).scalars().all()
    row_by_id = {row.id: row for row in rows}
    missing = [row_id for row_id in payload.ordered_ids if row_id not in row_by_id]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown tile IDs in reorder payload: {', '.join(missing)}",
        )

    next_sort = 10
    seen: set[str] = set()
    for row_id in payload.ordered_ids:
        row = row_by_id[row_id]
        row.sort_order = next_sort
        db.add(row)
        next_sort += 10
        seen.add(row_id)

    for row in rows:
        if row.id in seen:
            continue
        row.sort_order = next_sort
        db.add(row)
        next_sort += 10

    db.commit()
    refreshed = db.execute(
        select(OrganizationTile)
        .where(OrganizationTile.organization_id == organization.id)
        .order_by(OrganizationTile.sort_order.asc(), OrganizationTile.title.asc())
    ).scalars().all()
    return [_tile_read(row) for row in refreshed]


@router.get("/organization/announcements", response_model=list[AnnouncementRead])
def list_announcements(
    include_inactive: bool = Query(False),
    for_settings: bool = Query(False),
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
) -> list[AnnouncementRead]:
    if for_settings and not has_permission(membership.role, "org:manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    query = select(Announcement).where(Announcement.organization_id == organization.id)
    today = _today_date()
    if not include_inactive:
        query = query.where(
            Announcement.is_active.is_(True),
            Announcement.start_date <= today,
            (Announcement.end_date.is_(None) | (Announcement.end_date >= today)),
        )
    rows = db.execute(
        query.order_by(Announcement.start_date.desc(), Announcement.created_at.desc())
    ).scalars().all()
    return [_announcement_read(row) for row in rows]


@router.post(
    "/organization/announcements",
    response_model=AnnouncementRead,
    status_code=status.HTTP_201_CREATED,
)
def create_announcement(
    payload: AnnouncementCreate,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("org:manage")),
) -> AnnouncementRead:
    if payload.end_date and payload.end_date < payload.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date cannot be before start_date",
        )
    row = Announcement(
        organization_id=organization.id,
        title=payload.title.strip(),
        body=payload.body.strip(),
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_active=payload.is_active,
        created_by_user_id=membership.user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    log_event(
        db,
        action="announcement.created",
        entity_type="announcement",
        entity_id=row.id,
        organization_id=organization.id,
        actor=membership.user.email,
    )
    return _announcement_read(row)


@router.patch("/organization/announcements/{announcement_id}", response_model=AnnouncementRead)
def update_announcement(
    announcement_id: str,
    payload: AnnouncementUpdate,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("org:manage")),
) -> AnnouncementRead:
    row = db.execute(
        select(Announcement).where(
            Announcement.id == announcement_id,
            Announcement.organization_id == organization.id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found")

    start_date = payload.start_date if payload.start_date is not None else row.start_date
    end_date = payload.end_date if "end_date" in payload.model_fields_set else row.end_date
    if end_date and end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date cannot be before start_date",
        )

    if payload.title is not None:
        row.title = payload.title.strip()
    if payload.body is not None:
        row.body = payload.body.strip()
    row.start_date = start_date
    row.end_date = end_date
    if payload.is_active is not None:
        row.is_active = payload.is_active

    db.add(row)
    db.commit()
    db.refresh(row)

    log_event(
        db,
        action="announcement.updated",
        entity_type="announcement",
        entity_id=row.id,
        organization_id=organization.id,
        actor=membership.user.email,
    )
    return _announcement_read(row)


@router.get("/me/work-summary", response_model=WorkSummaryResponse)
def me_work_summary(
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
) -> WorkSummaryResponse:
    show_widget = membership.role in CLINICAL_OR_SUPERVISORY_ROLES
    if not show_widget:
        return WorkSummaryResponse(show_widget=False, items=[])

    items: list[WorkSummaryItem] = []

    notes_count = 0
    items.append(
        WorkSummaryItem(
            key="notes_requiring_signature",
            title="Notes requiring my signature",
            count=notes_count,
            href="/organization/home?panel=signatures",
        )
    )

    missing_paperwork_count = 0
    if has_permission(membership.role, "documents:read"):
        missing_paperwork_count = len(
            db.execute(
                select(PatientDocument.id)
                .join(
                    PatientServiceEnrollment,
                    PatientServiceEnrollment.id == PatientDocument.enrollment_id,
                )
                .where(
                    PatientDocument.organization_id == organization.id,
                    PatientDocument.status.in_(("required", "sent")),
                    PatientServiceEnrollment.organization_id == organization.id,
                    PatientServiceEnrollment.assigned_staff_user_id == membership.user_id,
                    PatientServiceEnrollment.status == "active",
                )
            ).all()
        )
    items.append(
        WorkSummaryItem(
            key="missing_paperwork",
            title="Patients missing required paperwork",
            count=missing_paperwork_count,
            href="/organization/home?panel=paperwork",
        )
    )

    upcoming_count = 0
    if has_permission(membership.role, "encounters:read"):
        now = utc_now()
        end_window = now + timedelta(days=7)
        upcoming_count = len(
            db.execute(
                select(Encounter.id).where(
                    and_(
                        Encounter.organization_id == organization.id,
                        Encounter.start_time >= now,
                        Encounter.start_time < end_window,
                    )
                )
            ).all()
        )
    items.append(
        WorkSummaryItem(
            key="upcoming_appointments",
            title="Upcoming appointments",
            count=upcoming_count,
            href="/scheduling",
        )
    )

    items.append(
        WorkSummaryItem(
            key="training_incomplete",
            title="Trainings assigned and incomplete",
            count=0,
            href="/organization/home?panel=training",
        )
    )
    return WorkSummaryResponse(show_widget=True, items=items)
