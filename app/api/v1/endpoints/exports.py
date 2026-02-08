from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, get_current_organization, require_permission
from app.db.models.disclosure_log import DisclosureLog
from app.db.models.patient import Patient
from app.db.models.patient_note import PatientNote
from app.db.models.service import Service
from app.db.session import get_db
from app.services.audit import log_event


router = APIRouter(tags=["Exports"])


class CourtStatusExportRequest(BaseModel):
    service_id: str
    start_date: date | None = None
    end_date: date | None = None


class ExportedNoteRead(BaseModel):
    id: str
    created_at: datetime
    body: str
    visibility: str


class CourtStatusExportResponse(BaseModel):
    patient_id: str
    service_id: str
    service_code: str
    start_date: date | None = None
    end_date: date | None = None
    disclosure_log_id: str
    note_count: int
    notes: list[ExportedNoteRead]


def _date_start(value: date) -> datetime:
    return datetime.combine(value, time.min).replace(tzinfo=timezone.utc)


def _date_end_exclusive(value: date) -> datetime:
    return _date_start(value) + timedelta(days=1)


@router.post(
    "/patients/{patient_id}/exports/court-status",
    response_model=CourtStatusExportResponse,
)
def export_court_status(
    patient_id: str,
    payload: CourtStatusExportRequest,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("patients:read")),
) -> CourtStatusExportResponse:
    if payload.start_date and payload.end_date and payload.end_date < payload.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date cannot be before start_date",
        )

    patient = db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.organization_id == organization.id,
        )
    ).scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    service = db.execute(
        select(Service).where(
            Service.id == payload.service_id,
            Service.organization_id == organization.id,
        )
    ).scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    if service.category != "sud":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Court status exports are restricted to SUD services",
        )

    filters = [
        PatientNote.organization_id == organization.id,
        PatientNote.patient_id == patient.id,
        PatientNote.primary_service_id == service.id,
        PatientNote.visibility == "legal_and_clinical",
    ]
    if payload.start_date:
        filters.append(PatientNote.created_at >= _date_start(payload.start_date))
    if payload.end_date:
        filters.append(PatientNote.created_at < _date_end_exclusive(payload.end_date))

    notes = db.execute(
        select(PatientNote)
        .where(and_(*filters))
        .order_by(PatientNote.created_at.asc())
    ).scalars().all()

    disclosure = DisclosureLog(
        organization_id=organization.id,
        patient_id=patient.id,
        service_id=service.id,
        generated_by_user_id=membership.user_id,
        export_type="court_status",
        start_date=payload.start_date,
        end_date=payload.end_date,
        disclosed_note_count=len(notes),
    )
    db.add(disclosure)
    db.commit()
    db.refresh(disclosure)

    log_event(
        db,
        action="court_export.generated",
        entity_type="court_export",
        entity_id=disclosure.id,
        organization_id=organization.id,
        patient_id=patient.id,
        actor=membership.user.email,
        metadata={
            "service_id": service.id,
            "service_code": service.code,
            "disclosure_log_id": disclosure.id,
            "note_count": len(notes),
            "start_date": payload.start_date.isoformat() if payload.start_date else None,
            "end_date": payload.end_date.isoformat() if payload.end_date else None,
        },
    )

    return CourtStatusExportResponse(
        patient_id=patient.id,
        service_id=service.id,
        service_code=service.code,
        start_date=payload.start_date,
        end_date=payload.end_date,
        disclosure_log_id=disclosure.id,
        note_count=len(notes),
        notes=[
            ExportedNoteRead(
                id=note.id,
                created_at=note.created_at,
                body=note.body,
                visibility=note.visibility,
            )
            for note in notes
        ],
    )
