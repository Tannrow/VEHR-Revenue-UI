import os
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, get_current_organization, require_permission
from app.db.models.document import Document
from app.db.models.encounter import Encounter
from app.db.models.patient import Patient
from app.db.session import get_db
from app.services.audit import log_event
from app.services.outbox import enqueue_event
from app.services.storage import (
    build_object_key,
    generate_presigned_get_url,
    get_s3_settings,
    upload_fileobj,
)


router = APIRouter(tags=["Documents"])


class DocumentRead(BaseModel):
    id: str
    patient_id: str | None = None
    encounter_id: str | None = None
    filename: str
    content_type: str | None = None
    size_bytes: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentDownload(BaseModel):
    url: str
    expires_in: int


def _get_file_size(upload: UploadFile) -> int:
    try:
        upload.file.seek(0, os.SEEK_END)
        size = upload.file.tell()
        upload.file.seek(0)
        return size
    except Exception:
        return 0


def _build_storage_key(
    organization_id: str,
    patient_id: str | None,
    document_id: str,
    filename: str,
) -> str:
    del patient_id
    return build_object_key(
        organization_id=organization_id,
        resource="documents",
        filename=filename,
        object_id=document_id,
    )


@router.post("/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload_document(
    file: UploadFile = File(...),
    patient_id: str | None = Form(None),
    encounter_id: str | None = Form(None),
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("documents:write")),
) -> DocumentRead:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing filename")

    if encounter_id:
        encounter = db.execute(
            select(Encounter).where(
                Encounter.id == encounter_id,
                Encounter.organization_id == organization.id,
            )
        ).scalar_one_or_none()
        if not encounter:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encounter not found")
        if patient_id and encounter.patient_id != patient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Encounter does not belong to patient",
            )
        if not patient_id:
            patient_id = encounter.patient_id

    if patient_id:
        patient = db.execute(
            select(Patient).where(
                Patient.id == patient_id,
                Patient.organization_id == organization.id,
            )
        ).scalar_one_or_none()
        if not patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    try:
        settings = get_s3_settings()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    document_id = str(uuid4())
    storage_key = _build_storage_key(
        organization_id=organization.id,
        patient_id=patient_id,
        document_id=document_id,
        filename=file.filename,
    )

    content_type = file.content_type or None
    size_bytes = _get_file_size(file)

    try:
        upload_fileobj(
            file_obj=file.file,
            key=storage_key,
            content_type=content_type,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Storage upload failed",
        ) from exc

    document = Document(
        id=document_id,
        organization_id=organization.id,
        patient_id=patient_id,
        encounter_id=encounter_id,
        uploaded_by_user_id=membership.user.id,
        filename=file.filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_provider="s3",
        storage_bucket=settings.bucket,
        storage_key=storage_key,
        storage_region=settings.region,
        storage_url=None,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    log_event(
        db,
        action="upload_document",
        entity_type="document",
        entity_id=document.id,
        organization_id=organization.id,
        patient_id=patient_id,
        actor=membership.user.email,
    )
    enqueue_event(
        db,
        organization_id=organization.id,
        event_type="document.uploaded",
        payload={
            "document_id": document.id,
            "patient_id": document.patient_id,
            "encounter_id": document.encounter_id,
            "filename": document.filename,
        },
    )

    return document


@router.get("/documents", response_model=list[DocumentRead])
def list_documents(
    patient_id: str | None = Query(None),
    encounter_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    _: None = Depends(require_permission("documents:read")),
) -> list[DocumentRead]:
    query = select(Document).where(Document.organization_id == organization.id)
    if patient_id:
        query = query.where(Document.patient_id == patient_id)
    if encounter_id:
        query = query.where(Document.encounter_id == encounter_id)
    documents = (
        db.execute(query.offset(offset).limit(limit))
        .scalars()
        .all()
    )
    return documents


@router.get("/patients/{patient_id}/uploaded-documents", response_model=list[DocumentRead])
def list_documents_for_patient(
    patient_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    _: None = Depends(require_permission("documents:read")),
) -> list[DocumentRead]:
    documents = (
        db.execute(
            select(Document)
            .where(
                Document.patient_id == patient_id,
                Document.organization_id == organization.id,
            )
            .offset(offset)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return documents


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("documents:read")),
) -> DocumentRead:
    document = db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.organization_id == organization.id,
        )
    ).scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    log_event(
        db,
        action="view_document",
        entity_type="document",
        entity_id=document.id,
        organization_id=organization.id,
        patient_id=document.patient_id,
        actor=membership.user.email,
    )
    return document


@router.get("/documents/{document_id}/download", response_model=DocumentDownload)
def download_document(
    document_id: str,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("documents:read")),
) -> DocumentDownload:
    document = db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.organization_id == organization.id,
        )
    ).scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    try:
        settings = get_s3_settings()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    url = generate_presigned_get_url(
        key=document.storage_key,
        expires=settings.presign_expires_seconds,
    )

    log_event(
        db,
        action="download_document",
        entity_type="document",
        entity_id=document.id,
        organization_id=organization.id,
        patient_id=document.patient_id,
        actor=membership.user.email,
    )

    return DocumentDownload(url=url, expires_in=settings.presign_expires_seconds)
