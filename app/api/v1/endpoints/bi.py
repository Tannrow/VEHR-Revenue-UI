from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, require_permission
from app.db.models.bi_report import BIReport
from app.db.models.organization_membership import OrganizationMembership
from app.db.session import get_db
from app.services.audit import log_event
from app.services.bi import PowerBIClient, PowerBIServiceError

router = APIRouter(prefix="/bi", tags=["Business Intelligence"])


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
    report_key: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("analytics:view")),
) -> BIEmbedConfigResponse:
    report_record = _enabled_report_or_404(db=db, report_key=report_key)
    org_id = membership.organization_id

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
        },
    )

    return BIEmbedConfigResponse(
        reportId=report.id,
        embedUrl=report.embed_url,
        accessToken=embed_token.token,
        expiresOn=embed_token.expires_on,
    )
