import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_membership, get_current_organization, require_permission
from app.core.portal_security import (
    create_portal_magic_token,
    generate_portal_code,
    hash_portal_code,
)
from app.core.time import utc_now
from app.db.models.form_template import FormTemplate
from app.db.models.patient import Patient
from app.db.models.patient_document import PatientDocument
from app.db.models.portal_access_code import PortalAccessCode
from app.db.models.service import Service
from app.db.models.service_document_template import ServiceDocumentTemplate
from app.db.session import get_db
from app.services.audit import log_event
from app.services.paperwork import expire_outdated_patient_documents


router = APIRouter(tags=["Paperwork"])

REQUIREMENT_TYPES = {"required", "optional"}
TRIGGERS = {"on_enrollment", "annual"}
PATIENT_DOCUMENT_STATUSES = {"required", "sent", "completed", "expired"}


class ServiceSummary(BaseModel):
    id: str
    name: str
    code: str
    category: str

    model_config = ConfigDict(from_attributes=True)


class FormTemplateSummary(BaseModel):
    id: str
    name: str
    version: int
    status: str

    model_config = ConfigDict(from_attributes=True)


class ServiceDocumentTemplateCreate(BaseModel):
    template_id: str
    requirement_type: str
    trigger: str
    validity_days: int | None = Field(default=None, ge=1, le=3650)


class ServiceDocumentTemplateUpdate(BaseModel):
    requirement_type: str | None = None
    trigger: str | None = None
    validity_days: int | None = Field(default=None, ge=1, le=3650)


class ServiceDocumentTemplateRead(BaseModel):
    id: str
    service_id: str
    template_id: str
    requirement_type: str
    trigger: str
    validity_days: int | None = None
    created_at: datetime
    service: ServiceSummary
    template: FormTemplateSummary


class PatientDocumentRead(BaseModel):
    id: str
    patient_id: str
    service_id: str
    enrollment_id: str
    template_id: str
    status: str
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    service: ServiceSummary
    template: FormTemplateSummary


class SendPatientDocumentsRequest(BaseModel):
    service_id: str | None = None
    patient_document_ids: list[str] | None = None
    expires_in_hours: int = Field(default=24, ge=1, le=168)


class SendPatientDocumentsResponse(BaseModel):
    sent_document_ids: list[str]
    access_code: str
    magic_link: str
    expires_at: datetime


def _normalize_requirement_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in REQUIREMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid requirement_type. Expected one of: {', '.join(sorted(REQUIREMENT_TYPES))}",
        )
    return normalized


def _normalize_trigger(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in TRIGGERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid trigger. Expected one of: {', '.join(sorted(TRIGGERS))}",
        )
    return normalized


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


def _get_template_or_404(db: Session, *, template_id: str, organization_id: str) -> FormTemplate:
    template = db.execute(
        select(FormTemplate).where(
            FormTemplate.id == template_id,
            FormTemplate.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Form template not found")
    return template


def _portal_login_base_url() -> str:
    configured = os.getenv("PATIENT_PORTAL_BASE_URL", "").strip()
    if configured:
        return configured
    return "https://the-trapp-house.com/portal/login"


def _to_service_document_template_read(row: ServiceDocumentTemplate) -> ServiceDocumentTemplateRead:
    return ServiceDocumentTemplateRead(
        id=row.id,
        service_id=row.service_id,
        template_id=row.template_id,
        requirement_type=row.requirement_type,
        trigger=row.trigger,
        validity_days=row.validity_days,
        created_at=row.created_at,
        service=ServiceSummary.model_validate(row.service),
        template=FormTemplateSummary.model_validate(row.template),
    )


def _to_patient_document_read(row: PatientDocument) -> PatientDocumentRead:
    if row.status not in PATIENT_DOCUMENT_STATUSES:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid patient document status")
    return PatientDocumentRead(
        id=row.id,
        patient_id=row.patient_id,
        service_id=row.service_id,
        enrollment_id=row.enrollment_id,
        template_id=row.template_id,
        status=row.status,
        completed_at=row.completed_at,
        expires_at=row.expires_at,
        sent_at=row.sent_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        service=ServiceSummary.model_validate(row.service),
        template=FormTemplateSummary.model_validate(row.template),
    )


@router.get(
    "/services/{service_id}/document-templates",
    response_model=list[ServiceDocumentTemplateRead],
)
def list_service_document_templates(
    service_id: str,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    _: None = Depends(require_permission("services:read")),
) -> list[ServiceDocumentTemplateRead]:
    _get_service_or_404(db, service_id=service_id, organization_id=organization.id)
    rows = db.execute(
        select(ServiceDocumentTemplate)
        .options(
            selectinload(ServiceDocumentTemplate.service),
            selectinload(ServiceDocumentTemplate.template),
        )
        .where(
            ServiceDocumentTemplate.organization_id == organization.id,
            ServiceDocumentTemplate.service_id == service_id,
        )
        .order_by(
            ServiceDocumentTemplate.requirement_type.asc(),
            ServiceDocumentTemplate.trigger.asc(),
            ServiceDocumentTemplate.created_at.asc(),
        )
    ).scalars().all()
    return [_to_service_document_template_read(row) for row in rows]


@router.post(
    "/services/{service_id}/document-templates",
    response_model=ServiceDocumentTemplateRead,
    status_code=status.HTTP_201_CREATED,
)
def create_service_document_template(
    service_id: str,
    payload: ServiceDocumentTemplateCreate,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("services:write")),
) -> ServiceDocumentTemplateRead:
    service = _get_service_or_404(db, service_id=service_id, organization_id=organization.id)
    template = _get_template_or_404(
        db,
        template_id=payload.template_id,
        organization_id=organization.id,
    )
    requirement_type = _normalize_requirement_type(payload.requirement_type)
    trigger = _normalize_trigger(payload.trigger)

    existing = db.execute(
        select(ServiceDocumentTemplate).where(
            ServiceDocumentTemplate.organization_id == organization.id,
            ServiceDocumentTemplate.service_id == service.id,
            ServiceDocumentTemplate.template_id == template.id,
            ServiceDocumentTemplate.trigger == trigger,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Service document template already exists for this trigger",
        )

    row = ServiceDocumentTemplate(
        organization_id=organization.id,
        service_id=service.id,
        template_id=template.id,
        requirement_type=requirement_type,
        trigger=trigger,
        validity_days=payload.validity_days,
    )
    db.add(row)
    db.commit()
    row = db.execute(
        select(ServiceDocumentTemplate)
        .options(
            selectinload(ServiceDocumentTemplate.service),
            selectinload(ServiceDocumentTemplate.template),
        )
        .where(ServiceDocumentTemplate.id == row.id)
    ).scalar_one()

    log_event(
        db,
        action="service_document_template.created",
        entity_type="service_document_template",
        entity_id=row.id,
        organization_id=organization.id,
        actor=membership.user.email,
        metadata={
            "service_id": row.service_id,
            "template_id": row.template_id,
            "requirement_type": row.requirement_type,
            "trigger": row.trigger,
        },
    )
    return _to_service_document_template_read(row)


@router.patch(
    "/service-document-templates/{service_document_template_id}",
    response_model=ServiceDocumentTemplateRead,
)
def update_service_document_template(
    service_document_template_id: str,
    payload: ServiceDocumentTemplateUpdate,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("services:write")),
) -> ServiceDocumentTemplateRead:
    row = db.execute(
        select(ServiceDocumentTemplate)
        .options(
            selectinload(ServiceDocumentTemplate.service),
            selectinload(ServiceDocumentTemplate.template),
        )
        .where(
            ServiceDocumentTemplate.id == service_document_template_id,
            ServiceDocumentTemplate.organization_id == organization.id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service document template not found",
        )

    if payload.requirement_type is not None:
        row.requirement_type = _normalize_requirement_type(payload.requirement_type)
    if payload.trigger is not None:
        row.trigger = _normalize_trigger(payload.trigger)
    if payload.validity_days is not None:
        row.validity_days = payload.validity_days

    db.add(row)
    db.commit()
    row = db.execute(
        select(ServiceDocumentTemplate)
        .options(
            selectinload(ServiceDocumentTemplate.service),
            selectinload(ServiceDocumentTemplate.template),
        )
        .where(ServiceDocumentTemplate.id == row.id)
    ).scalar_one()

    log_event(
        db,
        action="service_document_template.updated",
        entity_type="service_document_template",
        entity_id=row.id,
        organization_id=organization.id,
        actor=membership.user.email,
    )
    return _to_service_document_template_read(row)


@router.get("/patients/{patient_id}/documents", response_model=list[PatientDocumentRead])
def list_patient_documents(
    patient_id: str,
    service_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    _: None = Depends(require_permission("documents:read")),
) -> list[PatientDocumentRead]:
    _get_patient_or_404(db, patient_id=patient_id, organization_id=organization.id)
    if service_id:
        _get_service_or_404(db, service_id=service_id, organization_id=organization.id)

    expire_outdated_patient_documents(
        db,
        organization_id=organization.id,
        patient_id=patient_id,
        service_id=service_id,
    )

    filters = [
        PatientDocument.organization_id == organization.id,
        PatientDocument.patient_id == patient_id,
    ]
    if service_id:
        filters.append(PatientDocument.service_id == service_id)

    rows = db.execute(
        select(PatientDocument)
        .options(
            selectinload(PatientDocument.service),
            selectinload(PatientDocument.template),
        )
        .where(and_(*filters))
        .order_by(PatientDocument.created_at.asc())
    ).scalars().all()
    return [_to_patient_document_read(row) for row in rows]


@router.post(
    "/patients/{patient_id}/documents/send",
    response_model=SendPatientDocumentsResponse,
)
def send_patient_documents_to_portal(
    patient_id: str,
    payload: SendPatientDocumentsRequest,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("documents:write")),
) -> SendPatientDocumentsResponse:
    _get_patient_or_404(db, patient_id=patient_id, organization_id=organization.id)
    if payload.service_id:
        _get_service_or_404(db, service_id=payload.service_id, organization_id=organization.id)

    expire_outdated_patient_documents(
        db,
        organization_id=organization.id,
        patient_id=patient_id,
        service_id=payload.service_id,
    )

    filters = [
        PatientDocument.organization_id == organization.id,
        PatientDocument.patient_id == patient_id,
        PatientDocument.status.in_(("required", "sent")),
    ]
    if payload.service_id:
        filters.append(PatientDocument.service_id == payload.service_id)
    if payload.patient_document_ids:
        filters.append(PatientDocument.id.in_(payload.patient_document_ids))

    rows = db.execute(
        select(PatientDocument).where(and_(*filters))
    ).scalars().all()
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching required/sent documents found",
        )

    now = utc_now()
    for row in rows:
        row.status = "sent"
        row.sent_at = now

    access_code_value = generate_portal_code()
    expires_at = now + timedelta(hours=payload.expires_in_hours)
    access_code = PortalAccessCode(
        organization_id=organization.id,
        patient_id=patient_id,
        patient_document_id=rows[0].id if len(rows) == 1 else None,
        code_hash=hash_portal_code(access_code_value),
        expires_at=expires_at,
    )
    db.add(access_code)
    db.commit()
    db.refresh(access_code)

    magic_token = create_portal_magic_token(
        patient_id=patient_id,
        organization_id=organization.id,
        access_code_id=access_code.id,
    )
    portal_url = _portal_login_base_url()
    separator = "&" if "?" in portal_url else "?"
    magic_link = f"{portal_url}{separator}magic_token={magic_token}"

    log_event(
        db,
        action="patient_documents.sent_to_portal",
        entity_type="patient_document_bundle",
        entity_id=access_code.id,
        organization_id=organization.id,
        patient_id=patient_id,
        actor=membership.user.email,
        metadata={
            "sent_document_ids": [row.id for row in rows],
            "service_id": payload.service_id,
            "expires_at": expires_at.isoformat(),
        },
    )

    return SendPatientDocumentsResponse(
        sent_document_ids=[row.id for row in rows],
        access_code=access_code_value,
        magic_link=magic_link,
        expires_at=expires_at,
    )
