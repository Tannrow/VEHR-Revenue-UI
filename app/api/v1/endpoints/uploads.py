import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, get_current_organization, require_permission
from app.db.session import get_db
from app.services.audit import log_event
from app.services.s3_presign import (
    generate_presigned_get_url,
    generate_presigned_put_url,
    get_presign_s3_client,
    load_presign_s3_settings,
)


router = APIRouter(tags=["Uploads"])


class PresignUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=120)


class PresignUploadResponse(BaseModel):
    key: str
    url: str
    method: str
    headers: dict[str, str]


class PresignDownloadResponse(BaseModel):
    url: str


def _sanitize_filename(filename: str) -> str:
    safe_name = Path(filename).name
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", safe_name)
    if not safe_name:
        return "file"
    return safe_name[:180]


def _build_upload_key(filename: str, organization_id: str) -> str:
    now = datetime.now(timezone.utc)
    safe_name = _sanitize_filename(filename)
    return f"uploads/orgs/{organization_id}/{now:%Y/%m}/{uuid4()}_{safe_name}"


def _normalize_content_type(content_type: str) -> str:
    normalized = content_type.strip().lower()
    if not normalized:
        return "application/octet-stream"
    if any(ch in normalized for ch in ("\n", "\r", ";")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid content_type",
        )
    if "/" not in normalized:
        return "application/octet-stream"
    return normalized


@router.post("/uploads/presign", response_model=PresignUploadResponse)
def create_presigned_upload(
    payload: PresignUploadRequest,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("documents:write")),
) -> PresignUploadResponse:
    content_type = _normalize_content_type(payload.content_type)
    try:
        settings = load_presign_s3_settings()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    key = _build_upload_key(payload.filename, organization.id)
    client = get_presign_s3_client(settings)

    try:
        url = generate_presigned_put_url(
            client=client,
            bucket=settings.bucket,
            key=key,
            content_type=content_type,
            expires_in=settings.expires_in_seconds,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate upload URL",
        ) from exc

    log_event(
        db,
        action="create_upload_presign",
        entity_type="upload",
        entity_id=key,
        organization_id=organization.id,
        actor=membership.user.email,
    )

    return PresignUploadResponse(
        key=key,
        url=url,
        method="PUT",
        headers={"Content-Type": content_type},
    )


@router.get("/uploads/{key:path}/download", response_model=PresignDownloadResponse)
def create_presigned_download(
    key: str,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("documents:read")),
) -> PresignDownloadResponse:
    key = key.lstrip("/")
    required_prefix = f"uploads/orgs/{organization.id}/"
    if not key or not key.startswith(required_prefix):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid key",
        )

    try:
        settings = load_presign_s3_settings()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    client = get_presign_s3_client(settings)

    try:
        url = generate_presigned_get_url(
            client=client,
            bucket=settings.bucket,
            key=key,
            expires_in=settings.expires_in_seconds,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate download URL",
        ) from exc

    log_event(
        db,
        action="create_download_presign",
        entity_type="upload",
        entity_id=key,
        organization_id=organization.id,
        actor=membership.user.email,
    )

    return PresignDownloadResponse(url=url)
