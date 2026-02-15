from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db.models.analytics_alert import AnalyticsAlert
from app.db.models.analytics_metric import AnalyticsMetric
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.rpt_kpi_daily import RptKpiDaily
from app.db.models.rpt_kpi_snapshot import RptKpiSnapshot
from app.db.models.user import User
from app.db.session import SessionLocal, engine

logger = logging.getLogger(__name__)

BASELINE_WINDOWS_DAYS: tuple[int, ...] = (7, 30, 90)

# Curated set used by the Executive experience + KPI strip.
DEFAULT_ALERT_METRIC_KEYS: tuple[str, ...] = (
    "active_clients",
    "encounters_week",
    "charges_week",
    "claims_paid_week",
    "denial_rate_week",
    "ar_balance_total",
    "unsigned_notes_over_72h",
)

ALERT_TYPE_ANOMALY = "anomaly"
COMPARISON_PERIOD = "current_vs_prior"

STATUS_OPEN = "open"
STATUS_ACK = "acknowledged"
STATUS_RESOLVED = "resolved"

SEVERITY_INFO = "info"
SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"
SEVERITY_CRITICAL = "critical"

SEVERITY_THRESHOLDS_PCT: tuple[tuple[str, float], ...] = (
    (SEVERITY_CRITICAL, 50.0),
    (SEVERITY_HIGH, 35.0),
    (SEVERITY_MEDIUM, 20.0),
    (SEVERITY_LOW, 10.0),
    (SEVERITY_INFO, 5.0),
)

EPSILON = Decimal("0.000001")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _is_postgres() -> bool:
    return engine.dialect.name == "postgresql"


def _advisory_lock(conn: sa.Connection, lock_id: int) -> bool:
    """Best-effort single-run guard for Postgres."""
    if not _is_postgres():
        return True
    try:
        row = conn.execute(sa.text("SELECT pg_try_advisory_lock(:id)"), {"id": lock_id}).scalar_one()
        return bool(row)
    except Exception:
        logger.exception("Unable to acquire advisory lock")
        return False


def _advisory_unlock(conn: sa.Connection, lock_id: int) -> None:
    if not _is_postgres():
        return
    try:
        conn.execute(sa.text("SELECT pg_advisory_unlock(:id)"), {"id": lock_id})
    except Exception:
        logger.exception("Unable to release advisory lock")


def _title_case_from_key(key: str) -> str:
    return " ".join(part.capitalize() for part in key.split("_") if part)


def _is_rate_metric(metric_key: str) -> bool:
    return "rate" in metric_key.lower()


def _as_date(value: dt.date | dt.datetime) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    return value


@dataclass(frozen=True)
class WindowPair:
    current_start: dt.date
    current_end: dt.date
    baseline_start: dt.date
    baseline_end: dt.date


def _window_pair(*, as_of_date: dt.date, window_days: int) -> WindowPair:
    # Use inclusive date bounds. as_of_date is "today" in UTC.
    current_end = as_of_date - dt.timedelta(days=1)
    current_start = current_end - dt.timedelta(days=window_days - 1)

    baseline_end = current_start - dt.timedelta(days=1)
    baseline_start = baseline_end - dt.timedelta(days=window_days - 1)

    return WindowPair(
        current_start=current_start,
        current_end=current_end,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
    )


def _severity_from_delta_pct(delta_pct: Decimal) -> str | None:
    delta_abs = float(abs(delta_pct))
    for severity, threshold in SEVERITY_THRESHOLDS_PCT:
        if delta_abs >= threshold:
            return severity
    return None


def _report_key_for_metric(metric: AnalyticsMetric) -> str | None:
    category = (metric.category or "").strip().lower()
    key = (metric.metric_key or "").strip().lower()
    if category in {"financial", "revenue"} or key.startswith("ar_") or "denial" in key or "claim" in key:
        return "revenue_cycle"
    if category == "compliance" or "unsigned" in key:
        return "compliance_risk"
    if category in {"clinical"}:
        return "clinical_delivery"
    return "executive_overview"


def _recommended_actions(metric: AnalyticsMetric, *, delta_value: Decimal) -> list[str]:
    key = metric.metric_key.lower()
    category = (metric.category or "").strip().lower()
    direction = "up" if delta_value > 0 else "down"

    if category in {"financial", "revenue"} or key.startswith("ar_") or "denial" in key or "claim" in key:
        return [
            "Review payer mix and denial reasons for the current period; validate eligibility and authorization checks.",
            f"Investigate drivers behind {direction} movement (AR aging, submissions cadence, payment posting timelines).",
        ]
    if category == "compliance" or "unsigned" in key:
        return [
            "Route unsigned documentation to responsible staff and monitor SLA adherence (24h/72h).",
            "Slice by facility/program/provider to identify the main backlog drivers and assign owners.",
        ]
    if "encounter" in key or "admission" in key or "discharge" in key:
        return [
            "Review scheduling and staffing coverage for the largest swing days in the current period.",
            "Slice by facility/program to identify where volume shifted and validate operational drivers.",
        ]
    return [
        "Validate the metric movement by slicing facility/program/provider and confirm owners for follow-up actions.",
    ]


def _daily_aggregate(
    db: Session,
    *,
    tenant_id: str,
    metric_key: str,
    start: dt.date,
    end: dt.date,
) -> Decimal | None:
    agg = func.avg(RptKpiDaily.value_num) if _is_rate_metric(metric_key) else func.sum(RptKpiDaily.value_num)
    value = db.execute(
        select(agg).where(
            RptKpiDaily.tenant_id == tenant_id,
            RptKpiDaily.metric_key == metric_key,
            RptKpiDaily.kpi_date >= start,
            RptKpiDaily.kpi_date <= end,
        )
    ).scalar_one_or_none()
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _snapshot_latest(
    db: Session,
    *,
    tenant_id: str,
    metric_key: str,
    start: dt.date,
    end: dt.date,
) -> Decimal | None:
    # Prefer latest in-window. If no in-window value exists, fall back to latest <= end.
    in_window = db.execute(
        select(RptKpiSnapshot.value_num)
        .where(
            RptKpiSnapshot.tenant_id == tenant_id,
            RptKpiSnapshot.metric_key == metric_key,
            func.date(RptKpiSnapshot.as_of_ts) >= start,
            func.date(RptKpiSnapshot.as_of_ts) <= end,
            RptKpiSnapshot.value_num.is_not(None),
        )
        .order_by(RptKpiSnapshot.as_of_ts.desc())
        .limit(1)
    ).scalar_one_or_none()
    if in_window is not None:
        return in_window if isinstance(in_window, Decimal) else Decimal(str(in_window))

    fallback = db.execute(
        select(RptKpiSnapshot.value_num)
        .where(
            RptKpiSnapshot.tenant_id == tenant_id,
            RptKpiSnapshot.metric_key == metric_key,
            func.date(RptKpiSnapshot.as_of_ts) <= end,
            RptKpiSnapshot.value_num.is_not(None),
        )
        .order_by(RptKpiSnapshot.as_of_ts.desc())
        .limit(1)
    ).scalar_one_or_none()
    if fallback is None:
        return None
    return fallback if isinstance(fallback, Decimal) else Decimal(str(fallback))


def _metric_value(
    db: Session,
    *,
    tenant_id: str,
    metric: AnalyticsMetric,
    start: dt.date,
    end: dt.date,
) -> Decimal | None:
    if metric.grain == "daily" and metric.backing_table == "rpt_kpi_daily":
        return _daily_aggregate(db, tenant_id=tenant_id, metric_key=metric.metric_key, start=start, end=end)
    if metric.grain == "snapshot" and metric.backing_table == "rpt_kpi_snapshot":
        return _snapshot_latest(db, tenant_id=tenant_id, metric_key=metric.metric_key, start=start, end=end)
    return None


def _dedupe_key(*, org_id: str, metric_key: str, window_days: int, current_end: dt.date) -> str:
    return f"{org_id}:{metric_key}:{window_days}:{current_end.isoformat()}"


def _upsert_alert(
    db: Session,
    *,
    org_id: str,
    metric: AnalyticsMetric,
    window_days: int,
    windows: WindowPair,
    current_value: Decimal,
    baseline_value: Decimal,
    delta_value: Decimal,
    delta_pct: Decimal | None,
    severity: str,
    title: str,
    summary: str,
    recommended_actions: list[str],
) -> tuple[str, str]:
    dedupe = _dedupe_key(
        org_id=org_id,
        metric_key=metric.metric_key,
        window_days=window_days,
        current_end=windows.current_end,
    )
    existing = db.execute(
        select(AnalyticsAlert).where(
            AnalyticsAlert.organization_id == org_id,
            AnalyticsAlert.dedupe_key == dedupe,
        )
    ).scalar_one_or_none()

    if existing:
        existing.alert_type = ALERT_TYPE_ANOMALY
        existing.metric_key = metric.metric_key
        existing.report_key = _report_key_for_metric(metric)
        existing.baseline_window_days = window_days
        existing.comparison_period = COMPARISON_PERIOD
        existing.current_range_start = windows.current_start
        existing.current_range_end = windows.current_end
        existing.baseline_range_start = windows.baseline_start
        existing.baseline_range_end = windows.baseline_end
        existing.current_value = current_value
        existing.baseline_value = baseline_value
        existing.delta_value = delta_value
        existing.delta_pct = delta_pct
        existing.severity = severity
        existing.title = title
        existing.summary = summary
        existing.recommended_actions = recommended_actions
        existing.context_filters = {}
        existing.updated_at = utc_now()
        db.add(existing)
        return "updated", existing.id

    alert = AnalyticsAlert(
        id=str(uuid4()),
        organization_id=org_id,
        alert_type=ALERT_TYPE_ANOMALY,
        metric_key=metric.metric_key,
        report_key=_report_key_for_metric(metric),
        baseline_window_days=window_days,
        comparison_period=COMPARISON_PERIOD,
        current_range_start=windows.current_start,
        current_range_end=windows.current_end,
        baseline_range_start=windows.baseline_start,
        baseline_range_end=windows.baseline_end,
        current_value=current_value,
        baseline_value=baseline_value,
        delta_value=delta_value,
        delta_pct=delta_pct,
        severity=severity,
        title=title,
        summary=summary,
        recommended_actions=recommended_actions,
        context_filters={},
        status=STATUS_OPEN,
        acknowledged_at=None,
        resolved_at=None,
        dedupe_key=dedupe,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(alert)
    return "created", alert.id


def _eligible_metrics(db: Session) -> list[AnalyticsMetric]:
    requested = {key.strip().lower() for key in DEFAULT_ALERT_METRIC_KEYS if key.strip()}
    rows = (
        db.execute(
            select(AnalyticsMetric).where(AnalyticsMetric.metric_key.in_(sorted(requested)))
        )
        .scalars()
        .all()
    )
    return rows


def _org_ids(db: Session) -> list[str]:
    return db.execute(select(Organization.id).order_by(Organization.created_at.asc())).scalars().all()


def _compute_alert_for_metric(
    db: Session,
    *,
    org_id: str,
    metric: AnalyticsMetric,
    window_days: int,
    as_of_date: dt.date,
) -> tuple[str, str] | None:
    windows = _window_pair(as_of_date=as_of_date, window_days=window_days)

    current_value = _metric_value(
        db,
        tenant_id=org_id,
        metric=metric,
        start=windows.current_start,
        end=windows.current_end,
    )
    baseline_value = _metric_value(
        db,
        tenant_id=org_id,
        metric=metric,
        start=windows.baseline_start,
        end=windows.baseline_end,
    )

    if current_value is None or baseline_value is None:
        logger.debug(
            "skip metric=%s org_id=%s window=%sd missing_current=%s missing_baseline=%s",
            metric.metric_key,
            org_id,
            window_days,
            current_value is None,
            baseline_value is None,
        )
        return None

    delta_value = current_value - baseline_value

    if abs(delta_value) <= EPSILON and abs(baseline_value) <= EPSILON and abs(current_value) <= EPSILON:
        return None

    delta_pct: Decimal | None = None
    severity: str | None = None
    baseline_too_small = abs(baseline_value) <= EPSILON
    if not baseline_too_small:
        delta_pct = (delta_value / abs(baseline_value)) * Decimal("100")
        severity = _severity_from_delta_pct(delta_pct)
        if severity is None:
            return None
    else:
        # Deterministic fallback: baseline too small to compute percent change.
        severity = SEVERITY_INFO

    label = _title_case_from_key(metric.metric_key)
    direction = "up" if delta_value > 0 else "down" if delta_value < 0 else "flat"

    if delta_pct is not None:
        title = f"{label} {direction} {abs(float(delta_pct)):.1f}% vs prior {window_days}d"
        summary = (
            f"{label} is {direction} versus the prior {window_days}-day window. "
            f"Current ({windows.current_start.isoformat()} to {windows.current_end.isoformat()}) = {current_value}. "
            f"Baseline ({windows.baseline_start.isoformat()} to {windows.baseline_end.isoformat()}) = {baseline_value}. "
            f"Delta = {delta_value} ({delta_pct:+.1f}%)."
        )
    else:
        title = f"{label} changed vs prior {window_days}d"
        summary = (
            f"{label} changed versus the prior {window_days}-day window, but the baseline value was too small to "
            "compute a reliable percent change. "
            f"Current ({windows.current_start.isoformat()} to {windows.current_end.isoformat()}) = {current_value}. "
            f"Baseline ({windows.baseline_start.isoformat()} to {windows.baseline_end.isoformat()}) = {baseline_value}. "
            f"Delta = {delta_value}."
        )

    actions = _recommended_actions(metric, delta_value=delta_value)

    result = _upsert_alert(
        db,
        org_id=org_id,
        metric=metric,
        window_days=window_days,
        windows=windows,
        current_value=current_value,
        baseline_value=baseline_value,
        delta_value=delta_value,
        delta_pct=delta_pct,
        severity=severity,
        title=title,
        summary=summary,
        recommended_actions=actions,
    )
    return result


def generate_alerts(*, as_of_date: dt.date | None = None) -> None:
    reference = as_of_date or utc_now().date()

    if reference < dt.date(2000, 1, 1):
        raise RuntimeError("as_of_date appears invalid")

    # Avoid overlaps when scheduled: keep an advisory lock open for the duration of the run.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as lock_conn:
        lock_id = 360_601
        if not _advisory_lock(lock_conn, lock_id):
            logger.warning("alert generation already running (advisory lock busy); exiting.")
            return

        db = SessionLocal()
        try:
            metrics = _eligible_metrics(db)
            metric_map = {m.metric_key: m for m in metrics}
            org_ids = _org_ids(db)

            logger.info(
                "alerts.generate start as_of=%s orgs=%s metrics=%s",
                reference.isoformat(),
                len(org_ids),
                len(metrics),
            )

            failures: list[str] = []
            total_created = 0
            total_updated = 0
            total_evaluated = 0
            total_skipped = 0

            for org_id in org_ids:
                org_t0 = time.perf_counter()
                org_created = 0
                org_updated = 0
                org_evaluated = 0
                org_skipped = 0

                try:
                    for metric_key in DEFAULT_ALERT_METRIC_KEYS:
                        metric = metric_map.get(metric_key)
                        if not metric:
                            org_skipped += len(BASELINE_WINDOWS_DAYS)
                            continue
                        for window_days in BASELINE_WINDOWS_DAYS:
                            org_evaluated += 1
                            total_evaluated += 1
                            try:
                                outcome = _compute_alert_for_metric(
                                    db,
                                    org_id=org_id,
                                    metric=metric,
                                    window_days=window_days,
                                    as_of_date=reference,
                                )
                            except SQLAlchemyError:
                                raise
                            except Exception:
                                logger.exception(
                                    "alert computation failed org_id=%s metric_key=%s window=%s",
                                    org_id,
                                    metric.metric_key,
                                    window_days,
                                )
                                org_skipped += 1
                                total_skipped += 1
                                continue

                            if outcome is None:
                                org_skipped += 1
                                total_skipped += 1
                                continue

                            kind, _alert_id = outcome
                            if kind == "created":
                                org_created += 1
                                total_created += 1
                            else:
                                org_updated += 1
                                total_updated += 1

                    db.commit()
                except IntegrityError:
                    # Unique constraint conflicts are possible on concurrent runs; retry by re-running once after rollback.
                    db.rollback()
                    logger.warning("dedupe conflict org_id=%s; retrying once", org_id)
                    try:
                        for metric_key in DEFAULT_ALERT_METRIC_KEYS:
                            metric = metric_map.get(metric_key)
                            if not metric:
                                continue
                            for window_days in BASELINE_WINDOWS_DAYS:
                                _compute_alert_for_metric(
                                    db,
                                    org_id=org_id,
                                    metric=metric,
                                    window_days=window_days,
                                    as_of_date=reference,
                                )
                        db.commit()
                    except Exception as exc:
                        db.rollback()
                        failures.append(org_id)
                        logger.exception("org alert generation failed after retry org_id=%s error=%s", org_id, str(exc))
                except Exception as exc:
                    db.rollback()
                    failures.append(org_id)
                    logger.exception("org alert generation failed org_id=%s error=%s", org_id, str(exc))

                duration_ms = int((time.perf_counter() - org_t0) * 1000)
                logger.info(
                    "alerts.generate org_id=%s created=%s updated=%s evaluated=%s skipped=%s duration_ms=%s",
                    org_id,
                    org_created,
                    org_updated,
                    org_evaluated,
                    org_skipped,
                    duration_ms,
                )

            logger.info(
                "alerts.generate complete created=%s updated=%s evaluated=%s skipped=%s failures=%s",
                total_created,
                total_updated,
                total_evaluated,
                total_skipped,
                len(failures),
            )
            if failures:
                logger.warning("alerts.generate failures org_ids=%s", ",".join(failures))
        finally:
            db.close()
            _advisory_unlock(lock_conn, lock_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate anomaly alerts from governed KPI tables.")
    parser.add_argument("--as-of", type=str, default="", help="As-of date (YYYY-MM-DD). Defaults to today (UTC).")
    parser.add_argument("--log-level", type=str, default="INFO", help="Logging level (INFO, DEBUG, ...).")
    args = parser.parse_args(argv)

    _configure_logging(args.log_level)

    as_of_date: dt.date | None = None
    if args.as_of.strip():
        try:
            as_of_date = dt.date.fromisoformat(args.as_of.strip())
        except ValueError:
            logger.error("--as-of must be YYYY-MM-DD")
            return 2

    try:
        generate_alerts(as_of_date=as_of_date)
    except Exception:
        logger.exception("alerts.generate failed")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
