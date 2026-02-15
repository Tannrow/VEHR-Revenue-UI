from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, require_permission
from app.db.models.organization_membership import OrganizationMembership
from app.db.session import get_db
from app.services.audit import log_event
from app.services.bi import PowerBIClient, PowerBIServiceError

router = APIRouter(tags=["Business Intelligence"])

REPORT_KEY_CHART_AUDIT = "chart_audit"
DEFAULT_PBI_RLS_ROLE = "TenantRLS"


@dataclass(frozen=True)
class PowerBIReportTarget:
    workspace_id: str
    report_id: str
    dataset_id: str
    rls_role: str


class BIEmbedConfigResponse(BaseModel):
    type: str
    reportId: str
    embedUrl: str
    accessToken: str
    expiresOn: str


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{name} is not configured",
        )
    return value


def _rls_role() -> str:
    return os.getenv("PBI_RLS_ROLE", DEFAULT_PBI_RLS_ROLE).strip() or DEFAULT_PBI_RLS_ROLE


def _resolve_report_target(report_key: str) -> PowerBIReportTarget:
    normalized_key = report_key.strip().lower()
    if normalized_key != REPORT_KEY_CHART_AUDIT:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown report key",
        )

    return PowerBIReportTarget(
        workspace_id=_required_env("PBI_WORKSPACE_ID"),
        report_id=_required_env("PBI_REPORT_ID_CHART_AUDIT"),
        dataset_id=_required_env("PBI_DATASET_ID_CHART_AUDIT"),
        rls_role=_rls_role(),
    )


@router.get("/bi/embed-config", response_model=BIEmbedConfigResponse)
def get_bi_embed_config(
    report_key: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("analytics:view")),
) -> BIEmbedConfigResponse:
    target = _resolve_report_target(report_key)
    org_id = membership.organization_id
    user_id = membership.user_id

    try:
        client = PowerBIClient.from_env()
        service_token = client.get_access_token()
        report = client.get_report(
            workspace_id=target.workspace_id,
            report_id=target.report_id,
            access_token=service_token,
        )
        embed_token = client.generate_report_embed_token(
            workspace_id=target.workspace_id,
            report_id=report.id,
            dataset_id=target.dataset_id,
            username=org_id,
            rls_role=target.rls_role,
            access_token=service_token,
        )
    except PowerBIServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    log_event(
        db,
        action="bi.embed_token_issued",
        entity_type="bi_report",
        entity_id=report_key,
        organization_id=org_id,
        actor=membership.user.email,
        metadata={
            "org_id": org_id,
            "user_id": user_id,
            "report_key": report_key,
        },
    )

    return BIEmbedConfigResponse(
        type="report",
        reportId=report.id,
        embedUrl=report.embed_url,
        accessToken=embed_token.token,
        expiresOn=embed_token.expires_on,
    )
