from __future__ import annotations

import datetime as dt
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, require_permission
from app.core.rbac import normalize_role_key
from app.db.models.analytics_metric import AnalyticsMetric
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.rpt_kpi_daily import RptKpiDaily
from app.db.models.rpt_kpi_snapshot import RptKpiSnapshot
from app.db.session import get_db
from app.services.audit import log_event

router = APIRouter(prefix="/analytics", tags=["Analytics"])

_DAILY_GRAIN = "daily"
_SNAPSHOT_GRAIN = "snapshot"
_DAILY_TABLE = "rpt_kpi_daily"
_SNAPSHOT_TABLE = "rpt_kpi_snapshot"


class AnalyticsMetricRead(BaseModel):
    metric_key: str
    description: str | None = None
    category: str
    grain: str
    backing_table: str


class AnalyticsQueryRow(BaseModel):
    kpi_date: dt.date | None = None
    as_of_ts: dt.datetime | None = None
    value_num: float | None = None
    value_json: dict | list | None = None
    facility_id: str | None = None
    program_id: str | None = None
    provider_id: str | None = None
    payer_id: str | None = None


class AnalyticsQueryResponse(BaseModel):
    metric_key: str
    grain: str
    start: dt.date | None = None
    end: dt.date | None = None
    rows: list[AnalyticsQueryRow]


def _normalize_metric_key(metric_key: str) -> str:
    normalized = metric_key.strip().lower()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="metric_key is required")
    return normalized


def _normalize_role(role: str) -> str:
    normalized = normalize_role_key(role)
    return normalized or role.strip().lower()


def _is_role_allowed(metric: AnalyticsMetric, role: str) -> bool:
    allowed = {_normalize_role(str(item)) for item in (metric.allowed_roles or []) if str(item).strip()}
    return _normalize_role(role) in allowed


def _metric_or_404(db: Session, metric_key: str) -> AnalyticsMetric:
    row = db.execute(
        select(AnalyticsMetric).where(AnalyticsMetric.metric_key == metric_key)
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metric key not found")
    return row


def _uuid_string_or_400(value: str, *, field_name: str) -> str:
    try:
        return str(UUID(str(value)))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name}. Expected UUID string.",
        ) from exc


def _optional_uuid_filter(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    return _uuid_string_or_400(candidate, field_name=field_name)


def _decimal_to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


@router.get("/metrics", response_model=list[AnalyticsMetricRead])
def list_analytics_metrics(
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("analytics:view")),
) -> list[AnalyticsMetricRead]:
    rows = (
        db.execute(select(AnalyticsMetric).order_by(AnalyticsMetric.metric_key.asc()))
        .scalars()
        .all()
    )
    return [
        AnalyticsMetricRead(
            metric_key=row.metric_key,
            description=row.description,
            category=row.category,
            grain=row.grain,
            backing_table=row.backing_table,
        )
        for row in rows
        if _is_role_allowed(row, membership.role)
    ]


@router.get("/query", response_model=AnalyticsQueryResponse)
def query_analytics_metric(
    metric_key: str = Query(..., min_length=1),
    start: dt.date | None = Query(default=None),
    end: dt.date | None = Query(default=None),
    facility_id: str | None = Query(default=None),
    program_id: str | None = Query(default=None),
    provider_id: str | None = Query(default=None),
    payer_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("analytics:view")),
) -> AnalyticsQueryResponse:
    if start and end and start > end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start cannot be after end")

    normalized_metric_key = _normalize_metric_key(metric_key)
    metric = _metric_or_404(db, normalized_metric_key)
    if not _is_role_allowed(metric, membership.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Metric access denied for your role")

    tenant_id = _uuid_string_or_400(membership.organization_id, field_name="organization_id")
    facility_filter = _optional_uuid_filter(facility_id, field_name="facility_id")
    program_filter = _optional_uuid_filter(program_id, field_name="program_id")
    provider_filter = _optional_uuid_filter(provider_id, field_name="provider_id")
    payer_filter = _optional_uuid_filter(payer_id, field_name="payer_id")

    query_rows: list[AnalyticsQueryRow] = []

    if metric.grain == _DAILY_GRAIN and metric.backing_table == _DAILY_TABLE:
        query = select(RptKpiDaily).where(
            RptKpiDaily.tenant_id == tenant_id,
            RptKpiDaily.metric_key == metric.metric_key,
        )
        if start:
            query = query.where(RptKpiDaily.kpi_date >= start)
        if end:
            query = query.where(RptKpiDaily.kpi_date <= end)
        if facility_filter:
            query = query.where(RptKpiDaily.facility_id == facility_filter)
        if program_filter:
            query = query.where(RptKpiDaily.program_id == program_filter)
        if provider_filter:
            query = query.where(RptKpiDaily.provider_id == provider_filter)
        if payer_filter:
            query = query.where(RptKpiDaily.payer_id == payer_filter)

        rows = (
            db.execute(query.order_by(RptKpiDaily.kpi_date.asc()).limit(5000))
            .scalars()
            .all()
        )
        query_rows = [
            AnalyticsQueryRow(
                kpi_date=row.kpi_date,
                value_num=_decimal_to_float(row.value_num),
                value_json=row.value_json,
                facility_id=row.facility_id,
                program_id=row.program_id,
                provider_id=row.provider_id,
                payer_id=row.payer_id,
            )
            for row in rows
        ]
    elif metric.grain == _SNAPSHOT_GRAIN and metric.backing_table == _SNAPSHOT_TABLE:
        query = select(RptKpiSnapshot).where(
            RptKpiSnapshot.tenant_id == tenant_id,
            RptKpiSnapshot.metric_key == metric.metric_key,
        )
        if start:
            query = query.where(func.date(RptKpiSnapshot.as_of_ts) >= start)
        if end:
            query = query.where(func.date(RptKpiSnapshot.as_of_ts) <= end)
        if facility_filter:
            query = query.where(RptKpiSnapshot.facility_id == facility_filter)
        if program_filter:
            query = query.where(RptKpiSnapshot.program_id == program_filter)
        if provider_filter:
            query = query.where(RptKpiSnapshot.provider_id == provider_filter)
        if payer_filter:
            query = query.where(RptKpiSnapshot.payer_id == payer_filter)

        rows = (
            db.execute(query.order_by(RptKpiSnapshot.as_of_ts.asc()).limit(5000))
            .scalars()
            .all()
        )
        query_rows = [
            AnalyticsQueryRow(
                as_of_ts=row.as_of_ts,
                value_num=_decimal_to_float(row.value_num),
                value_json=row.value_json,
                facility_id=row.facility_id,
                program_id=row.program_id,
                provider_id=row.provider_id,
                payer_id=row.payer_id,
            )
            for row in rows
        ]
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Metric configuration is invalid. Expected supported grain/backing_table mapping.",
        )

    log_event(
        db,
        action="analytics.query",
        entity_type="analytics_metric",
        entity_id=metric.metric_key,
        organization_id=tenant_id,
        actor=membership.user.email,
        metadata={
            "org_id": tenant_id,
            "user_id": membership.user_id,
            "metric_key": metric.metric_key,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "facility_id": facility_filter,
            "program_id": program_filter,
            "provider_id": provider_filter,
            "payer_id": payer_filter,
            "row_count": len(query_rows),
        },
    )

    return AnalyticsQueryResponse(
        metric_key=metric.metric_key,
        grain=metric.grain,
        start=start,
        end=end,
        rows=query_rows,
    )
