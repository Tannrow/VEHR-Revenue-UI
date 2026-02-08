from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_membership, get_current_organization, require_permission
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.patient import Patient
from app.db.models.patient_note import PatientNote
from app.db.models.patient_service_enrollment import PatientServiceEnrollment
from app.db.models.service import Service
from app.db.models.user import User
from app.db.session import get_db
from app.services.audit import log_event


router = APIRouter(tags=["Services"])

SERVICE_CATEGORIES = {"intake", "sud", "mh", "psych", "cm"}
ENROLLMENT_STATUSES = {"active", "paused", "discharged"}
NOTE_VISIBILITIES = {"clinical_only", "legal_and_clinical"}


class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=50)
    category: str
    is_active: bool = True
    sort_order: int = 0


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(default=None, min_length=1, max_length=50)
    category: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class ServiceRead(BaseModel):
    id: str
    name: str
    code: str
    category: str
    is_active: bool
    sort_order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EnrollmentCreate(BaseModel):
    service_id: str
    status: str = "active"
    start_date: date
    end_date: date | None = None
    assigned_staff_user_id: str | None = None
    reporting_enabled: bool = False


class EnrollmentUpdate(BaseModel):
    status: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    assigned_staff_user_id: str | None = None
    reporting_enabled: bool | None = None


class ServiceSummary(BaseModel):
    id: str
    name: str
    code: str
    category: str

    model_config = ConfigDict(from_attributes=True)


class EnrollmentRead(BaseModel):
    id: str
    patient_id: str
    service_id: str
    status: str
    start_date: date
    end_date: date | None
    assigned_staff_user_id: str | None
    reporting_enabled: bool
    created_at: datetime
    updated_at: datetime
    service: ServiceSummary


class NoteCreate(BaseModel):
    primary_service_id: str
    body: str = Field(min_length=1)
    visibility: str = "clinical_only"


class NoteRead(BaseModel):
    id: str
    patient_id: str
    primary_service_id: str
    visibility: str
    body: str
    created_by_user_id: str | None = None
    created_at: datetime
    primary_service: ServiceSummary


def _normalize_category(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in SERVICE_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Expected one of: {', '.join(sorted(SERVICE_CATEGORIES))}",
        )
    return normalized


def _normalize_status(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in ENROLLMENT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Expected one of: {', '.join(sorted(ENROLLMENT_STATUSES))}",
        )
    return normalized


def _normalize_visibility(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in NOTE_VISIBILITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid visibility. Expected one of: {', '.join(sorted(NOTE_VISIBILITIES))}",
        )
    return normalized


def _normalize_service_code(value: str) -> str:
    code = value.strip().upper().replace("-", "_").replace(" ", "_")
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="code is required",
        )
    return code


def _get_patient_or_404(db: Session, *, patient_id: str, organization_id: str) -> Patient:
    patient = db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return patient


def _get_service_or_404(db: Session, *, service_id: str, organization_id: str) -> Service:
    service = db.execute(
        select(Service).where(
            Service.id == service_id,
            Service.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return service


def _ensure_assigned_staff_in_org(
    db: Session,
    *,
    assigned_staff_user_id: str | None,
    organization_id: str,
) -> None:
    if assigned_staff_user_id is None:
        return

    membership = db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == assigned_staff_user_id,
        )
    ).scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assigned staff user is not a member of this organization",
        )

    user = db.get(User, assigned_staff_user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assigned staff user is not active",
        )


def _validate_date_window(*, start_date: date, end_date: date | None) -> None:
    if end_date is not None and end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date cannot be before start_date",
        )


def _windows_overlap(
    *,
    first_start: date,
    first_end: date | None,
    second_start: date,
    second_end: date | None,
) -> bool:
    first_window_end = first_end or date.max
    second_window_end = second_end or date.max
    return first_start <= second_window_end and second_start <= first_window_end


def _active_enrollment_query(
    *,
    organization_id: str,
    patient_id: str,
    exclude_enrollment_id: str | None = None,
):
    query = select(PatientServiceEnrollment).where(
        PatientServiceEnrollment.organization_id == organization_id,
        PatientServiceEnrollment.patient_id == patient_id,
        PatientServiceEnrollment.status == "active",
    )
    if exclude_enrollment_id:
        query = query.where(PatientServiceEnrollment.id != exclude_enrollment_id)
    return query


def _enforce_same_service_overlap_rule(
    db: Session,
    *,
    organization_id: str,
    patient_id: str,
    service_id: str,
    status_value: str,
    start_date: date,
    end_date: date | None,
    exclude_enrollment_id: str | None = None,
) -> None:
    if status_value != "active":
        return

    existing = db.execute(
        _active_enrollment_query(
            organization_id=organization_id,
            patient_id=patient_id,
            exclude_enrollment_id=exclude_enrollment_id,
        ).where(PatientServiceEnrollment.service_id == service_id)
    ).scalars().all()

    for enrollment in existing:
        if _windows_overlap(
            first_start=enrollment.start_date,
            first_end=enrollment.end_date,
            second_start=start_date,
            second_end=end_date,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Overlapping active enrollment exists for this service",
            )


def _enforce_sud_exclusivity_rule(
    db: Session,
    *,
    organization_id: str,
    patient_id: str,
    service: Service,
    status_value: str,
    start_date: date,
    end_date: date | None,
    exclude_enrollment_id: str | None = None,
) -> None:
    if status_value != "active" or service.category != "sud":
        return

    rows = db.execute(
        select(PatientServiceEnrollment, Service)
        .join(Service, Service.id == PatientServiceEnrollment.service_id)
        .where(
            PatientServiceEnrollment.organization_id == organization_id,
            PatientServiceEnrollment.patient_id == patient_id,
            PatientServiceEnrollment.status == "active",
            Service.category == "sud",
            Service.organization_id == organization_id,
        )
    ).all()

    for enrollment, other_service in rows:
        if exclude_enrollment_id and enrollment.id == exclude_enrollment_id:
            continue
        if _windows_overlap(
            first_start=enrollment.start_date,
            first_end=enrollment.end_date,
            second_start=start_date,
            second_end=end_date,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Only one active SUD enrollment is allowed at a time. "
                    f"Conflicts with service code {other_service.code}."
                ),
            )


def _to_enrollment_read(enrollment: PatientServiceEnrollment) -> EnrollmentRead:
    service = enrollment.service
    return EnrollmentRead(
        id=enrollment.id,
        patient_id=enrollment.patient_id,
        service_id=enrollment.service_id,
        status=enrollment.status,
        start_date=enrollment.start_date,
        end_date=enrollment.end_date,
        assigned_staff_user_id=enrollment.assigned_staff_user_id,
        reporting_enabled=enrollment.reporting_enabled,
        created_at=enrollment.created_at,
        updated_at=enrollment.updated_at,
        service=ServiceSummary(
            id=service.id,
            name=service.name,
            code=service.code,
            category=service.category,
        ),
    )


def _to_note_read(note: PatientNote) -> NoteRead:
    service = note.primary_service
    return NoteRead(
        id=note.id,
        patient_id=note.patient_id,
        primary_service_id=note.primary_service_id,
        visibility=note.visibility,
        body=note.body,
        created_by_user_id=note.created_by_user_id,
        created_at=note.created_at,
        primary_service=ServiceSummary(
            id=service.id,
            name=service.name,
            code=service.code,
            category=service.category,
        ),
    )


@router.get("/services", response_model=list[ServiceRead])
def list_services(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    _: None = Depends(require_permission("services:read")),
) -> list[ServiceRead]:
    query = select(Service).where(Service.organization_id == organization.id)
    if not include_inactive:
        query = query.where(Service.is_active.is_(True))
    services = db.execute(
        query.order_by(Service.sort_order.asc(), Service.name.asc())
    ).scalars().all()
    return services


@router.post("/services", response_model=ServiceRead, status_code=status.HTTP_201_CREATED)
def create_service(
    payload: ServiceCreate,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    _: None = Depends(require_permission("services:write")),
) -> ServiceRead:
    code = _normalize_service_code(payload.code)
    category = _normalize_category(payload.category)

    existing = db.execute(
        select(Service).where(
            Service.organization_id == organization.id,
            Service.code == code,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Service code already exists for this organization",
        )

    service = Service(
        organization_id=organization.id,
        name=payload.name.strip(),
        code=code,
        category=category,
        is_active=payload.is_active,
        sort_order=payload.sort_order,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.patch("/services/{service_id}", response_model=ServiceRead)
def update_service(
    service_id: str,
    payload: ServiceUpdate,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    _: None = Depends(require_permission("services:write")),
) -> ServiceRead:
    service = _get_service_or_404(db, service_id=service_id, organization_id=organization.id)

    if payload.code is not None:
        code = _normalize_service_code(payload.code)
        existing = db.execute(
            select(Service).where(
                Service.organization_id == organization.id,
                Service.code == code,
                Service.id != service.id,
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Service code already exists for this organization",
            )
        service.code = code

    if payload.name is not None:
        service.name = payload.name.strip()
    if payload.category is not None:
        service.category = _normalize_category(payload.category)
    if payload.is_active is not None:
        service.is_active = payload.is_active
    if payload.sort_order is not None:
        service.sort_order = payload.sort_order

    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.get("/patients/{patient_id}/enrollments", response_model=list[EnrollmentRead])
def list_patient_enrollments(
    patient_id: str,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    _: None = Depends(require_permission("patients:read")),
) -> list[EnrollmentRead]:
    _get_patient_or_404(db, patient_id=patient_id, organization_id=organization.id)

    enrollments = db.execute(
        select(PatientServiceEnrollment)
        .options(selectinload(PatientServiceEnrollment.service))
        .where(
            PatientServiceEnrollment.organization_id == organization.id,
            PatientServiceEnrollment.patient_id == patient_id,
        )
        .order_by(
            PatientServiceEnrollment.start_date.desc(),
            PatientServiceEnrollment.created_at.desc(),
        )
    ).scalars().all()
    return [_to_enrollment_read(enrollment) for enrollment in enrollments]


@router.post(
    "/patients/{patient_id}/enrollments",
    response_model=EnrollmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_patient_enrollment(
    patient_id: str,
    payload: EnrollmentCreate,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("patients:write")),
) -> EnrollmentRead:
    _get_patient_or_404(db, patient_id=patient_id, organization_id=organization.id)
    service = _get_service_or_404(db, service_id=payload.service_id, organization_id=organization.id)

    status_value = _normalize_status(payload.status)
    _validate_date_window(start_date=payload.start_date, end_date=payload.end_date)
    _ensure_assigned_staff_in_org(
        db,
        assigned_staff_user_id=payload.assigned_staff_user_id,
        organization_id=organization.id,
    )
    _enforce_same_service_overlap_rule(
        db,
        organization_id=organization.id,
        patient_id=patient_id,
        service_id=service.id,
        status_value=status_value,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    _enforce_sud_exclusivity_rule(
        db,
        organization_id=organization.id,
        patient_id=patient_id,
        service=service,
        status_value=status_value,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )

    enrollment = PatientServiceEnrollment(
        organization_id=organization.id,
        patient_id=patient_id,
        service_id=service.id,
        status=status_value,
        start_date=payload.start_date,
        end_date=payload.end_date,
        assigned_staff_user_id=payload.assigned_staff_user_id,
        reporting_enabled=payload.reporting_enabled,
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    enrollment = db.execute(
        select(PatientServiceEnrollment)
        .options(selectinload(PatientServiceEnrollment.service))
        .where(PatientServiceEnrollment.id == enrollment.id)
    ).scalar_one()

    log_event(
        db,
        action="enrollment.created",
        entity_type="patient_service_enrollment",
        entity_id=enrollment.id,
        organization_id=organization.id,
        patient_id=patient_id,
        actor=membership.user.email,
        metadata={
            "service_id": enrollment.service_id,
            "status": enrollment.status,
            "start_date": enrollment.start_date.isoformat(),
            "end_date": enrollment.end_date.isoformat() if enrollment.end_date else None,
        },
    )

    return _to_enrollment_read(enrollment)


@router.patch("/enrollments/{enrollment_id}", response_model=EnrollmentRead)
def update_enrollment(
    enrollment_id: str,
    payload: EnrollmentUpdate,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("patients:write")),
) -> EnrollmentRead:
    enrollment = db.execute(
        select(PatientServiceEnrollment)
        .options(selectinload(PatientServiceEnrollment.service))
        .where(
            PatientServiceEnrollment.id == enrollment_id,
            PatientServiceEnrollment.organization_id == organization.id,
        )
    ).scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")

    provided_fields = payload.model_fields_set
    status_value = _normalize_status(payload.status) if payload.status is not None else enrollment.status
    start_date = payload.start_date if payload.start_date is not None else enrollment.start_date
    end_date = payload.end_date if "end_date" in provided_fields else enrollment.end_date
    assigned_staff_user_id = (
        payload.assigned_staff_user_id
        if "assigned_staff_user_id" in provided_fields
        else enrollment.assigned_staff_user_id
    )

    _validate_date_window(start_date=start_date, end_date=end_date)
    _ensure_assigned_staff_in_org(
        db,
        assigned_staff_user_id=assigned_staff_user_id,
        organization_id=organization.id,
    )
    _enforce_same_service_overlap_rule(
        db,
        organization_id=organization.id,
        patient_id=enrollment.patient_id,
        service_id=enrollment.service_id,
        status_value=status_value,
        start_date=start_date,
        end_date=end_date,
        exclude_enrollment_id=enrollment.id,
    )
    _enforce_sud_exclusivity_rule(
        db,
        organization_id=organization.id,
        patient_id=enrollment.patient_id,
        service=enrollment.service,
        status_value=status_value,
        start_date=start_date,
        end_date=end_date,
        exclude_enrollment_id=enrollment.id,
    )

    enrollment.status = status_value
    enrollment.start_date = start_date
    enrollment.end_date = end_date
    enrollment.assigned_staff_user_id = assigned_staff_user_id
    if "reporting_enabled" in provided_fields:
        enrollment.reporting_enabled = payload.reporting_enabled

    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    enrollment = db.execute(
        select(PatientServiceEnrollment)
        .options(selectinload(PatientServiceEnrollment.service))
        .where(PatientServiceEnrollment.id == enrollment.id)
    ).scalar_one()

    log_event(
        db,
        action="enrollment.updated",
        entity_type="patient_service_enrollment",
        entity_id=enrollment.id,
        organization_id=organization.id,
        patient_id=enrollment.patient_id,
        actor=membership.user.email,
        metadata={
            "service_id": enrollment.service_id,
            "status": enrollment.status,
            "start_date": enrollment.start_date.isoformat(),
            "end_date": enrollment.end_date.isoformat() if enrollment.end_date else None,
            "assigned_staff_user_id": enrollment.assigned_staff_user_id,
            "reporting_enabled": enrollment.reporting_enabled,
        },
    )
    return _to_enrollment_read(enrollment)


@router.get("/patients/{patient_id}/notes", response_model=list[NoteRead])
def list_patient_notes(
    patient_id: str,
    service_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    _: None = Depends(require_permission("patients:read")),
) -> list[NoteRead]:
    _get_patient_or_404(db, patient_id=patient_id, organization_id=organization.id)
    if service_id:
        _get_service_or_404(db, service_id=service_id, organization_id=organization.id)

    filters = [
        PatientNote.organization_id == organization.id,
        PatientNote.patient_id == patient_id,
    ]
    if service_id:
        filters.append(PatientNote.primary_service_id == service_id)

    notes = db.execute(
        select(PatientNote)
        .options(selectinload(PatientNote.primary_service))
        .where(and_(*filters))
        .order_by(PatientNote.created_at.desc())
    ).scalars().all()
    return [_to_note_read(note) for note in notes]


@router.post("/patients/{patient_id}/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_patient_note(
    patient_id: str,
    payload: NoteCreate,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("patients:write")),
) -> NoteRead:
    _get_patient_or_404(db, patient_id=patient_id, organization_id=organization.id)
    service = _get_service_or_404(db, service_id=payload.primary_service_id, organization_id=organization.id)

    body = payload.body.strip()
    if not body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="body is required",
        )

    note = PatientNote(
        organization_id=organization.id,
        patient_id=patient_id,
        primary_service_id=service.id,
        visibility=_normalize_visibility(payload.visibility),
        body=body,
        created_by_user_id=membership.user_id,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    note = db.execute(
        select(PatientNote)
        .options(selectinload(PatientNote.primary_service))
        .where(PatientNote.id == note.id)
    ).scalar_one()
    return _to_note_read(note)
