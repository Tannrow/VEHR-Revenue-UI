from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from app.db.session import SessionLocal
from app.services.audit import log_event

logger = logging.getLogger(__name__)

router = APIRouter()

_DEPRECATION_PAYLOAD = {
    "deprecated": True,
    "message": "Use /api/v1/* endpoints. This endpoint will be removed.",
    "replacement": "/api/v1",
}


def _metadata(request: Request) -> dict[str, Any]:
    metadata = {
        "method": request.method,
        "path": request.url.path,
        "client": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "request_id": request.headers.get("x-request-id")
        or request.headers.get("x-requestid")
        or request.headers.get("x-correlation-id"),
        "forwarded_for": request.headers.get("x-forwarded-for"),
        "host": request.headers.get("host"),
        "organization_id": request.headers.get("x-organization-id"),
        "user_id": request.headers.get("x-user-id"),
    }
    return {k: v for k, v in metadata.items() if v is not None}


def _safe_audit(request: Request) -> None:
    try:
        db = SessionLocal()
    except Exception:
        logger.exception("legacy_api_root_session_failed")
        return

    try:
        metadata = _metadata(request)
        try:
            logger.warning(
                "legacy_api_root_hit %s",
                " ".join(f"{key}={value}" for key, value in metadata.items()),
            )
        except Exception:
            logger.exception("legacy_api_root_log_failed")
        log_event(
            db,
            action="platform.legacy_api_root_hit",
            entity_type="legacy_api",
            entity_id="legacy_api_root",
            organization_id=None,
            actor=None,
            metadata=metadata,
        )
    except Exception:
        logger.exception("legacy_api_root_audit_failed")
    finally:
        db.close()


@router.get("/api/")
@router.post("/api/")
@router.get("/api")
@router.post("/api")
async def legacy_api_root(request: Request) -> dict[str, str | bool]:
    _safe_audit(request)
    return _DEPRECATION_PAYLOAD
