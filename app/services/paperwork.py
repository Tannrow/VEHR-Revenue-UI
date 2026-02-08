from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db.models.patient_document import PatientDocument
from app.db.models.patient_service_enrollment import PatientServiceEnrollment
from app.db.models.service_document_template import ServiceDocumentTemplate


def _expires_at_from_validity_days(start_date: date, validity_days: int | None) -> datetime | None:
    if validity_days is None:
        return None
    start_of_day = datetime.combine(start_date, time.min).replace(tzinfo=timezone.utc)
    return start_of_day + timedelta(days=validity_days)


def assign_required_documents_for_enrollment(
    db: Session,
    *,
    enrollment: PatientServiceEnrollment,
) -> list[PatientDocument]:
    templates = db.execute(
        select(ServiceDocumentTemplate).where(
            ServiceDocumentTemplate.organization_id == enrollment.organization_id,
            ServiceDocumentTemplate.service_id == enrollment.service_id,
            ServiceDocumentTemplate.requirement_type == "required",
            ServiceDocumentTemplate.trigger == "on_enrollment",
        )
    ).scalars().all()

    created: list[PatientDocument] = []
    for template in templates:
        existing = db.execute(
            select(PatientDocument).where(
                PatientDocument.organization_id == enrollment.organization_id,
                PatientDocument.enrollment_id == enrollment.id,
                PatientDocument.template_id == template.template_id,
            )
        ).scalar_one_or_none()
        if existing:
            continue

        patient_document = PatientDocument(
            organization_id=enrollment.organization_id,
            patient_id=enrollment.patient_id,
            service_id=enrollment.service_id,
            enrollment_id=enrollment.id,
            template_id=template.template_id,
            service_document_template_id=template.id,
            status="required",
            completed_at=None,
            expires_at=_expires_at_from_validity_days(
                enrollment.start_date,
                template.validity_days,
            ),
            sent_at=None,
        )
        db.add(patient_document)
        created.append(patient_document)

    if created:
        db.commit()
        for row in created:
            db.refresh(row)
    return created


def expire_outdated_patient_documents(
    db: Session,
    *,
    organization_id: str,
    patient_id: str,
    service_id: str | None = None,
) -> int:
    now = utc_now()
    filters = [
        PatientDocument.organization_id == organization_id,
        PatientDocument.patient_id == patient_id,
        PatientDocument.status.in_(("required", "sent")),
        PatientDocument.expires_at.is_not(None),
        PatientDocument.expires_at < now,
    ]
    if service_id:
        filters.append(PatientDocument.service_id == service_id)

    rows = db.execute(
        select(PatientDocument).where(and_(*filters))
    ).scalars().all()
    for row in rows:
        row.status = "expired"
    if rows:
        db.commit()
    return len(rows)
