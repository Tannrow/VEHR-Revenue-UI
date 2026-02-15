from __future__ import annotations

import datetime as dt
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, require_permission
from app.core.rbac import normalize_role_key
from app.db.models.bi_report import BIReport
from app.db.models.organization_membership import OrganizationMembership
from app.db.session import get_db
from app.services.audit import log_event
from app.services.bi import PowerBIClient, PowerBIServiceError
from app.services.ttl_cache import TtlLruCache

router = APIRouter(prefix="/bi", tags=["Business Intelligence"])
logger = logging.getLogger(__name__)

_EMBED_CONFIG_CACHE_TTL_SECONDS = 600.0
_EMBED_CONFIG_CACHE_MAXSIZE = 256
_EMBED_CONFIG_CACHE = TtlLruCache(ttl_seconds=_EMBED_CONFIG_CACHE_TTL_SECONDS, maxsize=_EMBED_CONFIG_CACHE_MAXSIZE)
_CACHE_BYPASS_HEADER = "x-cache-bypass"


class BIReportRead(BaseModel):
    key: str
    name: str | None = None


class BIEmbedConfigResponse(BaseModel):
    reportId: str
    embedUrl: str
    accessToken: str
    expiresOn: str


def _enabled_report_or_404(*, db: Session, report_key: str) -> BIReport:
    normalized_key = report_key.strip().lower()
    row = db.execute(
        select(BIReport).where(
            BIReport.report_key == normalized_key,
            BIReport.is_enabled.is_(True),
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report key not found")
    return row


def _normalize_role(role: str) -> str:
    normalized = normalize_role_key(role)
    return normalized or (role or "").strip().lower()


def _cache_bypass_requested(request: Request) -> bool:
    raw = request.headers.get(_CACHE_BYPASS_HEADER, "").strip().lower()
    return raw in {"1", "true", "yes"}


def _cache_bypass_allowed(role: str) -> bool:
    normalized = _normalize_role(role)
    return normalized in {"admin", "office_manager", "sud_supervisor"}


def _parse_expires_on(expires_on: str) -> dt.datetime | None:
    raw = (expires_on or "").strip()
    if not raw:
        return None
    # Power BI returns ISO-8601 with Z suffix.
    candidate = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        parsed = dt.datetime.fromisoformat(candidate)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.UTC)
    return parsed


@router.get("/reports", response_model=list[BIReportRead])
def list_bi_reports(
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("analytics:view")),
) -> list[BIReportRead]:
    rows = (
        db.execute(
            select(BIReport)
            .where(BIReport.is_enabled.is_(True))
            .order_by(BIReport.report_key.asc())
        )
        .scalars()
        .all()
    )
    return [
        BIReportRead(
            key=row.report_key,
            name=row.name,
        )
        for row in rows
    ]


@router.get("/embed-config", response_model=BIEmbedConfigResponse)
def get_bi_embed_config(
    request: Request,
    report_key: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("analytics:view")),
) -> BIEmbedConfigResponse:
    t0 = time.perf_counter()
    report_record = _enabled_report_or_404(db=db, report_key=report_key)
    org_id = membership.organization_id

    cache_key = "|".join(
        [
            "bi.embed-config.v1",
            str(org_id),
            report_record.report_key,
            str(report_record.workspace_id),
            str(report_record.report_id),
            str(report_record.dataset_id),
            str(report_record.rls_role),
        ]
    )
    bypass_cache = _cache_bypass_requested(request) and _cache_bypass_allowed(membership.role)

    if not bypass_cache:
        cached, hit = _EMBED_CONFIG_CACHE.get(cache_key)
        if hit and isinstance(cached, BIEmbedConfigResponse):
            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "bi.embed-config cache_hit=1 report_key=%s org_id=%s duration_ms=%s",
                report_record.report_key,
                org_id,
                duration_ms,
            )
            return cached

    try:
        client = PowerBIClient.from_env()
        service_token = client.get_access_token()
        report = client.get_report(
            workspace_id=report_record.workspace_id,
            report_id=report_record.report_id,
            access_token=service_token,
        )
        embed_token = client.generate_report_embed_token(
            workspace_id=report_record.workspace_id,
            report_id=report.id,
            dataset_id=report_record.dataset_id,
            username=str(org_id),
            rls_role=report_record.rls_role,
            access_token=service_token,
        )
    except PowerBIServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    log_event(
        db,
        action="bi.embed_token_issued",
        entity_type="bi_report",
        entity_id=report_record.report_key,
        organization_id=org_id,
        actor=membership.user.email,
        metadata={
            "org_id": org_id,
            "user_id": membership.user_id,
            "report_key": report_record.report_key,
            "cache": {"hit": False, "bypass": bypass_cache},
            "duration_ms": int((time.perf_counter() - t0) * 1000),
        },
    )

    response = BIEmbedConfigResponse(
        reportId=report.id,
        embedUrl=report.embed_url,
        accessToken=embed_token.token,
        expiresOn=embed_token.expires_on,
    )

    if not bypass_cache:
        ttl_seconds = _EMBED_CONFIG_CACHE_TTL_SECONDS
        parsed_expiry = _parse_expires_on(response.expiresOn)
        if parsed_expiry:
            seconds_until_expiry = (parsed_expiry - dt.datetime.now(dt.UTC)).total_seconds()
            ttl_seconds = min(ttl_seconds, max(0.0, seconds_until_expiry - 120.0))
        if ttl_seconds >= 30.0:
            _EMBED_CONFIG_CACHE.set(cache_key, response, ttl_seconds=ttl_seconds)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "bi.embed-config cache_hit=0 report_key=%s org_id=%s duration_ms=%s ttl_s=%s",
            report_record.report_key,
            org_id,
            duration_ms,
            int(ttl_seconds),
        )

    return response
