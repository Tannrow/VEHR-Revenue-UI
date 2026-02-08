import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, selectinload

from app.core.portal_deps import get_portal_session
from app.core.portal_security import (
    create_portal_session_token,
    decode_portal_magic_token,
    hash_portal_code,
)
from app.core.time import utc_now
from app.db.models.form_submission import FormSubmission
from app.db.models.form_template import FormTemplate
from app.db.models.patient import Patient
from app.db.models.patient_document import PatientDocument
from app.db.models.portal_access_code import PortalAccessCode
from app.db.models.service import Service
from app.db.session import get_db
from app.services.audit import log_event
from app.services.paperwork import expire_outdated_patient_documents


router = APIRouter(tags=["Portal"])


class PortalLoginRequest(BaseModel):
    code: str | None = None
    patient_id: str | None = None
    email: str | None = None
    magic_token: str | None = None


class PortalLoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    patient_id: str
    organization_id: str


class PortalMeResponse(BaseModel):
    patient_id: str
    organization_id: str
    first_name: str
    last_name: str
    email: str | None = None
    required_count: int
    sent_count: int
    completed_count: int


class PortalServiceSummary(BaseModel):
    id: str
    name: str
    code: str
    category: str

    model_config = ConfigDict(from_attributes=True)


class PortalTemplateSummary(BaseModel):
    id: str
    name: str
    version: int
    schema_json_value: str = Field(alias="schema_json")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PortalDocumentItem(BaseModel):
    id: str
    status: str
    expires_at: str | None = None
    completed_at: str | None = None
    sent_at: str | None = None
    template: PortalTemplateSummary


class PortalDocumentGroup(BaseModel):
    service: PortalServiceSummary
    documents: list[PortalDocumentItem]


class PortalDocumentSubmitRequest(BaseModel):
    signature_name: str = Field(min_length=1, max_length=200)
    submitted_data: dict | None = None


class PortalDocumentSubmitResponse(BaseModel):
    patient_document_id: str
    form_submission_id: str
    status: str
    completed_at: str


def _get_document_for_portal(
    db: Session,
    *,
    patient_document_id: str,
    patient_id: str,
    organization_id: str,
) -> PatientDocument:
    row = db.execute(
        select(PatientDocument)
        .options(selectinload(PatientDocument.template))
        .where(
            PatientDocument.id == patient_document_id,
            PatientDocument.organization_id == organization_id,
            PatientDocument.patient_id == patient_id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return row


def _resolve_login_access_code(
    db: Session,
    payload: PortalLoginRequest,
) -> PortalAccessCode:
    now = utc_now()
    if payload.magic_token:
        try:
            token_data = decode_portal_magic_token(payload.magic_token)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid magic token",
            )
        row = db.execute(
            select(PortalAccessCode).where(
                PortalAccessCode.id == token_data.access_code_id,
                PortalAccessCode.organization_id == token_data.organization_id,
                PortalAccessCode.patient_id == token_data.patient_id,
            )
        ).scalar_one_or_none()
        if not row or row.expires_at < now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Magic token has expired",
            )
        return row

    if not payload.code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="code or magic_token is required",
        )
    if not payload.patient_id and not payload.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="patient_id or email is required with code login",
        )

    query = select(PortalAccessCode).where(
        PortalAccessCode.code_hash == hash_portal_code(payload.code),
        PortalAccessCode.expires_at >= now,
    )
    if payload.patient_id:
        query = query.where(PortalAccessCode.patient_id == payload.patient_id)
    if payload.email:
        query = query.join(Patient, Patient.id == PortalAccessCode.patient_id).where(
            Patient.email == payload.email.strip().lower(),
        )
    row = db.execute(
        query.order_by(PortalAccessCode.created_at.desc())
    ).scalars().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid portal code",
        )
    return row


@router.post("/portal/login", response_model=PortalLoginResponse)
def portal_login(
    payload: PortalLoginRequest,
    db: Session = Depends(get_db),
) -> PortalLoginResponse:
    row = _resolve_login_access_code(db, payload)
    row.used_at = utc_now()
    db.add(row)
    db.commit()

    access_token = create_portal_session_token(
        patient_id=row.patient_id,
        organization_id=row.organization_id,
    )
    return PortalLoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=60 * 60 * 12,
        patient_id=row.patient_id,
        organization_id=row.organization_id,
    )


@router.get("/portal/me", response_model=PortalMeResponse)
def portal_me(
    portal_session=Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> PortalMeResponse:
    _, patient, organization = portal_session
    expire_outdated_patient_documents(
        db,
        organization_id=organization.id,
        patient_id=patient.id,
    )
    rows = db.execute(
        select(PatientDocument.status).where(
            PatientDocument.organization_id == organization.id,
            PatientDocument.patient_id == patient.id,
        )
    ).all()
    counts: dict[str, int] = {"required": 0, "sent": 0, "completed": 0}
    for (status_value,) in rows:
        if status_value in counts:
            counts[status_value] += 1
    return PortalMeResponse(
        patient_id=patient.id,
        organization_id=organization.id,
        first_name=patient.first_name,
        last_name=patient.last_name,
        email=patient.email,
        required_count=counts["required"],
        sent_count=counts["sent"],
        completed_count=counts["completed"],
    )


@router.get("/portal/documents", response_model=list[PortalDocumentGroup])
def portal_documents(
    portal_session=Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> list[PortalDocumentGroup]:
    _, patient, organization = portal_session
    expire_outdated_patient_documents(
        db,
        organization_id=organization.id,
        patient_id=patient.id,
    )

    rows = db.execute(
        select(PatientDocument)
        .options(
            selectinload(PatientDocument.service),
            selectinload(PatientDocument.template),
        )
        .where(
            PatientDocument.organization_id == organization.id,
            PatientDocument.patient_id == patient.id,
        )
        .order_by(PatientDocument.created_at.asc())
    ).scalars().all()

    grouped: dict[str, PortalDocumentGroup] = {}
    for row in rows:
        service = row.service
        if service.id not in grouped:
            grouped[service.id] = PortalDocumentGroup(
                service=PortalServiceSummary.model_validate(service),
                documents=[],
            )
        grouped[service.id].documents.append(
            PortalDocumentItem(
                id=row.id,
                status=row.status,
                expires_at=row.expires_at.isoformat() if row.expires_at else None,
                completed_at=row.completed_at.isoformat() if row.completed_at else None,
                sent_at=row.sent_at.isoformat() if row.sent_at else None,
                template=PortalTemplateSummary(
                    id=row.template.id,
                    name=row.template.name,
                    version=row.template.version,
                    schema_json_value=row.template.schema_json,
                ),
            )
        )

    return list(grouped.values())


@router.post(
    "/portal/documents/{patient_document_id}/submit",
    response_model=PortalDocumentSubmitResponse,
)
def portal_submit_document(
    patient_document_id: str,
    payload: PortalDocumentSubmitRequest,
    portal_session=Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> PortalDocumentSubmitResponse:
    _, patient, organization = portal_session
    row = _get_document_for_portal(
        db,
        patient_document_id=patient_document_id,
        patient_id=patient.id,
        organization_id=organization.id,
    )
    if row.status == "expired":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document has expired and cannot be submitted",
        )
    if row.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document already completed",
        )

    template = db.execute(
        select(FormTemplate).where(
            FormTemplate.id == row.template_id,
            FormTemplate.organization_id == organization.id,
        )
    ).scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    if template.status != "published":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Template is not currently publishable in portal",
        )

    now = utc_now()
    submission_payload = payload.submitted_data.copy() if payload.submitted_data else {}
    submission_payload["_portal_signature_name"] = payload.signature_name.strip()
    submission_payload["_portal_submitted_at"] = now.isoformat()

    submission = FormSubmission(
        organization_id=organization.id,
        patient_id=patient.id,
        encounter_id=None,
        form_template_id=template.id,
        submitted_data_json=json.dumps(submission_payload),
        pdf_uri=None,
    )
    row.status = "completed"
    row.completed_at = now

    db.add(submission)
    db.add(row)
    db.commit()
    db.refresh(submission)
    db.refresh(row)

    log_event(
        db,
        action="portal.form_submitted",
        entity_type="patient_document",
        entity_id=row.id,
        organization_id=organization.id,
        patient_id=patient.id,
        actor=f"portal:{patient.id}",
        metadata={
            "form_submission_id": submission.id,
            "template_id": template.id,
        },
    )

    return PortalDocumentSubmitResponse(
        patient_document_id=row.id,
        form_submission_id=submission.id,
        status=row.status,
        completed_at=row.completed_at.isoformat() if row.completed_at else now.isoformat(),
    )
