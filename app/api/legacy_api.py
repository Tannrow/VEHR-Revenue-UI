from __future__ import annotations

import logging

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


def _safe_audit(request: Request) -> None:
    try:
        db = SessionLocal()
    except Exception:
        logger.exception("legacy_api_root_session_failed")
        return

    try:
        metadata = {
            "method": request.method,
            "path": request.url.path,
            "client": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
            "request_id": request.headers.get("x-request-id")
            or request.headers.get("x-requestid")
            or request.headers.get("x-correlation-id"),
        }
        log_event(
            db,
            action="platform.legacy_api_root_hit",
            entity_type="legacy_api",
            entity_id="legacy_api_root",
            organization_id=None,
            actor=None,
            metadata={k: v for k, v in metadata.items() if v is not None},
        )
    except Exception:
        logger.exception("legacy_api_root_audit_failed")
    finally:
        db.close()


@router.get("/api")
@router.post("/api")
async def legacy_api_root(request: Request) -> dict[str, str | bool]:
    _safe_audit(request)
    return _DEPRECATION_PAYLOAD
