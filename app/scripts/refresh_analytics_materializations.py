from __future__ import annotations

import argparse
import logging
import sys
import time
from uuid import uuid4

import sqlalchemy as sa

from app.db.models.rpt_kpi_daily import RptKpiDaily
from app.db.session import engine

logger = logging.getLogger(__name__)

# Materializations that feed the governed analytics layer.
_MV_KPI_DAILY_CORE = "reporting.mv_kpi_daily_core"

_MATERIALIZED_DAILY_METRIC_KEYS: tuple[str, ...] = (
    "encounters_week",
    "new_admissions_week",
    "discharges_week",
)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _is_postgres() -> bool:
    return engine.dialect.name == "postgresql"


def _advisory_lock(conn: sa.Connection, lock_id: int) -> bool:
    """Best-effort single-run guard for Postgres."""
    try:
        row = conn.execute(sa.text("SELECT pg_try_advisory_lock(:id)"), {"id": lock_id}).scalar_one()
        return bool(row)
    except Exception:
        logger.exception("Unable to acquire advisory lock")
        return False


def _advisory_unlock(conn: sa.Connection, lock_id: int) -> None:
    try:
        conn.execute(sa.text("SELECT pg_advisory_unlock(:id)"), {"id": lock_id})
    except Exception:
        logger.exception("Unable to release advisory lock")


def _matview_is_populated(conn: sa.Connection, *, schema: str, name: str) -> bool:
    row = conn.execute(
        sa.text(
            """
            SELECT ispopulated
            FROM pg_matviews
            WHERE schemaname = :schema AND matviewname = :name
            """
        ),
        {"schema": schema, "name": name},
    ).scalar_one_or_none()
    if row is None:
        raise RuntimeError(f"Materialized view not found: {schema}.{name}")
    return bool(row)


def refresh_materialized_views() -> None:
    if not _is_postgres():
        logger.info("Skipping refresh: materialized views require Postgres (dialect=%s).", engine.dialect.name)
        return

    schema, name = _MV_KPI_DAILY_CORE.split(".", 1)
    refresh_sql = f"REFRESH MATERIALIZED VIEW {_MV_KPI_DAILY_CORE}"
    refresh_concurrently_sql = f"REFRESH MATERIALIZED VIEW CONCURRENTLY {_MV_KPI_DAILY_CORE}"

    # REFRESH ... CONCURRENTLY cannot run inside a transaction block.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        lock_id = 360_501
        if not _advisory_lock(conn, lock_id):
            logger.warning("Refresh already running (advisory lock busy); exiting.")
            return

        try:
            is_populated = _matview_is_populated(conn, schema=schema, name=name)
            t0 = time.perf_counter()
            if is_populated:
                conn.execute(sa.text(refresh_concurrently_sql))
                kind = "concurrently"
            else:
                conn.execute(sa.text(refresh_sql))
                kind = "initial"
            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "refreshed %s kind=%s duration_ms=%s",
                _MV_KPI_DAILY_CORE,
                kind,
                duration_ms,
            )
        finally:
            _advisory_unlock(conn, lock_id)


def _delete_daily_totals(conn: sa.Connection) -> int:
    stmt = (
        sa.delete(RptKpiDaily)
        .where(RptKpiDaily.metric_key.in_(_MATERIALIZED_DAILY_METRIC_KEYS))
        .where(RptKpiDaily.facility_id.is_(None))
        .where(RptKpiDaily.program_id.is_(None))
        .where(RptKpiDaily.provider_id.is_(None))
        .where(RptKpiDaily.payer_id.is_(None))
    )
    result = conn.execute(stmt)
    return int(getattr(result, "rowcount", 0) or 0)


def sync_daily_kpis_from_materializations(*, batch_size: int = 1000) -> None:
    if not _is_postgres():
        logger.info("Skipping KPI sync: materialized views require Postgres (dialect=%s).", engine.dialect.name)
        return

    select_sql = sa.text(
        """
        SELECT
            tenant_id,
            kpi_date,
            metric_key,
            value_num,
            value_json,
            facility_id,
            program_id,
            provider_id,
            payer_id
        FROM reporting.mv_kpi_daily_core
        """
    )

    inserted = 0
    with engine.begin() as conn:
        t0 = time.perf_counter()
        deleted = _delete_daily_totals(conn)

        rows = conn.execute(select_sql).mappings()
        batch: list[dict] = []
        for row in rows:
            batch.append(
                {
                    "id": str(uuid4()),
                    "tenant_id": str(row["tenant_id"]),
                    "kpi_date": row["kpi_date"],
                    "metric_key": str(row["metric_key"]),
                    "value_num": row["value_num"],
                    "value_json": row["value_json"],
                    "facility_id": row["facility_id"],
                    "program_id": row["program_id"],
                    "provider_id": row["provider_id"],
                    "payer_id": row["payer_id"],
                }
            )
            if len(batch) >= batch_size:
                conn.execute(sa.insert(RptKpiDaily.__table__), batch)
                inserted += len(batch)
                batch.clear()

        if batch:
            conn.execute(sa.insert(RptKpiDaily.__table__), batch)
            inserted += len(batch)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "synced rpt_kpi_daily deleted=%s inserted=%s duration_ms=%s",
            deleted,
            inserted,
            duration_ms,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh analytics materializations and sync KPI tables.")
    parser.add_argument("--no-refresh", action="store_true", help="Skip refreshing materialized views.")
    parser.add_argument("--no-sync", action="store_true", help="Skip syncing KPI tables from materialized views.")
    parser.add_argument("--batch-size", type=int, default=1000, help="Insert batch size for KPI sync.")
    parser.add_argument("--log-level", type=str, default="INFO", help="Logging level (INFO, DEBUG, ...).")
    args = parser.parse_args(argv)

    _configure_logging(args.log_level)

    logger.info("analytics.refresh start no_refresh=%s no_sync=%s dialect=%s", args.no_refresh, args.no_sync, engine.dialect.name)
    try:
        if not args.no_refresh:
            refresh_materialized_views()
        if not args.no_sync:
            sync_daily_kpis_from_materializations(batch_size=max(1, int(args.batch_size)))
    except Exception:
        logger.exception("analytics.refresh failed")
        return 1

    logger.info("analytics.refresh complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

