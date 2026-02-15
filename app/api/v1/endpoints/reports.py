from __future__ import annotations

import datetime as dt
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, require_permission
from app.core.rbac import normalize_role_key
from app.db.models.analytics_metric import AnalyticsMetric
from app.db.models.generated_report import GeneratedReport
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.rpt_kpi_daily import RptKpiDaily
from app.db.models.rpt_kpi_snapshot import RptKpiSnapshot
from app.db.session import get_db
from app.services.audit import log_event

router = APIRouter(prefix="/reports", tags=["Reports"])

WEEKLY_EXEC_REPORT_KEY = "weekly_exec_overview"


class GeneratedReportRead(BaseModel):
    report_id: str
    report_key: str
    tenant_id: str
    period_start: dt.date
    period_end: dt.date
    generated_at: dt.datetime
    created_by: str | None = None
    content_json: dict


class GenerateWeeklyExecResponse(BaseModel):
    report_id: str
    report_key: str
    period_start: dt.date
    period_end: dt.date


def _uuid_string_or_400(value: str, *, field_name: str) -> str:
    try:
        return str(UUID(str(value)))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name}. Expected UUID string.",
        ) from exc


def _normalize_role(role: str) -> str:
    normalized = normalize_role_key(role)
    return normalized or role.strip().lower()


def _is_role_allowed(metric: AnalyticsMetric, role: str) -> bool:
    allowed = {_normalize_role(str(item)) for item in (metric.allowed_roles or []) if str(item).strip()}
    return _normalize_role(role) in allowed


def _decimal_to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _metric_label(metric_key: str) -> str:
    return " ".join(part.capitalize() for part in metric_key.split("_") if part)


def _weekly_window(today: dt.date | None = None) -> tuple[dt.date, dt.date]:
    reference = today or dt.date.today()
    period_start = reference - dt.timedelta(days=reference.weekday())
    period_end = period_start + dt.timedelta(days=6)
    return period_start, period_end


def _report_or_404(db: Session, *, tenant_id: str, report_id: str) -> GeneratedReport:
    row = db.execute(
        select(GeneratedReport).where(
            GeneratedReport.report_id == report_id,
            GeneratedReport.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated report not found")
    return row


def _serialize_report(report: GeneratedReport) -> GeneratedReportRead:
    return GeneratedReportRead(
        report_id=report.report_id,
        report_key=report.report_key,
        tenant_id=report.tenant_id,
        period_start=report.period_start,
        period_end=report.period_end,
        generated_at=report.generated_at,
        created_by=report.created_by,
        content_json=report.content_json,
    )


@router.get("/generated/{report_id}", response_model=GeneratedReportRead)
def get_generated_report(
    report_id: str,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("analytics:view")),
) -> GeneratedReportRead:
    tenant_id = _uuid_string_or_400(membership.organization_id, field_name="organization_id")
    report_uuid = _uuid_string_or_400(report_id, field_name="report_id")
    report = _report_or_404(db, tenant_id=tenant_id, report_id=report_uuid)
    return _serialize_report(report)


@router.get("/generated/latest", response_model=GeneratedReportRead)
def get_latest_generated_report(
    report_key: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("analytics:view")),
) -> GeneratedReportRead:
    tenant_id = _uuid_string_or_400(membership.organization_id, field_name="organization_id")
    normalized_key = report_key.strip().lower()
    row = db.execute(
        select(GeneratedReport)
        .where(
            GeneratedReport.tenant_id == tenant_id,
            GeneratedReport.report_key == normalized_key,
        )
        .order_by(GeneratedReport.generated_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No generated report found")
    return _serialize_report(row)


@router.post("/generate/weekly-exec", response_model=GenerateWeeklyExecResponse)
def generate_weekly_exec_overview(
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("analytics:view")),
) -> GenerateWeeklyExecResponse:
    tenant_id = _uuid_string_or_400(membership.organization_id, field_name="organization_id")
    created_by = _uuid_string_or_400(membership.user_id, field_name="user_id")
    period_start, period_end = _weekly_window()

    metrics = (
        db.execute(select(AnalyticsMetric).order_by(AnalyticsMetric.metric_key.asc()))
        .scalars()
        .all()
    )
    visible_metrics = [metric for metric in metrics if _is_role_allowed(metric, membership.role)]

    kpi_cards: list[dict] = []
    trend_series: list[dict] = []
    end_of_period_ts = dt.datetime.combine(period_end + dt.timedelta(days=1), dt.time.min, tzinfo=dt.UTC)

    for metric in visible_metrics:
        if metric.grain == "daily" and metric.backing_table == "rpt_kpi_daily":
            daily_rows = (
                db.execute(
                    select(RptKpiDaily)
                    .where(
                        RptKpiDaily.tenant_id == tenant_id,
                        RptKpiDaily.metric_key == metric.metric_key,
                        RptKpiDaily.kpi_date >= period_start,
                        RptKpiDaily.kpi_date <= period_end,
                    )
                    .order_by(RptKpiDaily.kpi_date.asc())
                )
                .scalars()
                .all()
            )
            latest_value = next(
                (_decimal_to_float(row.value_num) for row in reversed(daily_rows) if row.value_num is not None),
                None,
            )
            kpi_cards.append(
                {
                    "metric_key": metric.metric_key,
                    "label": _metric_label(metric.metric_key),
                    "category": metric.category,
                    "value_num": latest_value,
                    "point_count": len(daily_rows),
                }
            )
            trend_series.append(
                {
                    "metric_key": metric.metric_key,
                    "label": _metric_label(metric.metric_key),
                    "points": [
                        {
                            "x": row.kpi_date.isoformat(),
                            "y": _decimal_to_float(row.value_num),
                        }
                        for row in daily_rows
                        if row.value_num is not None
                    ],
                }
            )
        elif metric.grain == "snapshot" and metric.backing_table == "rpt_kpi_snapshot":
            snapshot_rows = (
                db.execute(
                    select(RptKpiSnapshot)
                    .where(
                        RptKpiSnapshot.tenant_id == tenant_id,
                        RptKpiSnapshot.metric_key == metric.metric_key,
                        func.date(RptKpiSnapshot.as_of_ts) >= period_start,
                        func.date(RptKpiSnapshot.as_of_ts) <= period_end,
                    )
                    .order_by(RptKpiSnapshot.as_of_ts.asc())
                )
                .scalars()
                .all()
            )
            if not snapshot_rows:
                fallback_latest = db.execute(
                    select(RptKpiSnapshot)
                    .where(
                        RptKpiSnapshot.tenant_id == tenant_id,
                        RptKpiSnapshot.metric_key == metric.metric_key,
                        RptKpiSnapshot.as_of_ts < end_of_period_ts,
                    )
                    .order_by(RptKpiSnapshot.as_of_ts.desc())
                    .limit(1)
                ).scalar_one_or_none()
                if fallback_latest:
                    snapshot_rows = [fallback_latest]

            latest_value = next(
                (_decimal_to_float(row.value_num) for row in reversed(snapshot_rows) if row.value_num is not None),
                None,
            )
            kpi_cards.append(
                {
                    "metric_key": metric.metric_key,
                    "label": _metric_label(metric.metric_key),
                    "category": metric.category,
                    "value_num": latest_value,
                    "point_count": len(snapshot_rows),
                }
            )
            trend_series.append(
                {
                    "metric_key": metric.metric_key,
                    "label": _metric_label(metric.metric_key),
                    "points": [
                        {
                            "x": row.as_of_ts.isoformat(),
                            "y": _decimal_to_float(row.value_num),
                        }
                        for row in snapshot_rows
                        if row.value_num is not None
                    ],
                }
            )

    content_json = {
        "title": "Weekly Executive Overview",
        "report_key": WEEKLY_EXEC_REPORT_KEY,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "sections": {
            "kpis": kpi_cards,
            "trends": trend_series,
            "anomalies": [],
            "recommended_actions": [],
        },
    }

    report = GeneratedReport(
        report_id=str(uuid4()),
        report_key=WEEKLY_EXEC_REPORT_KEY,
        tenant_id=tenant_id,
        period_start=period_start,
        period_end=period_end,
        generated_at=dt.datetime.now(dt.UTC),
        created_by=created_by,
        content_json=content_json,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    log_event(
        db,
        action="reports.generate_weekly_exec",
        entity_type="generated_report",
        entity_id=report.report_id,
        organization_id=tenant_id,
        actor=membership.user.email,
        metadata={
            "org_id": tenant_id,
            "user_id": membership.user_id,
            "report_key": WEEKLY_EXEC_REPORT_KEY,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "kpi_count": len(kpi_cards),
            "trend_count": len(trend_series),
        },
    )

    return GenerateWeeklyExecResponse(
        report_id=report.report_id,
        report_key=report.report_key,
        period_start=report.period_start,
        period_end=report.period_end,
    )
