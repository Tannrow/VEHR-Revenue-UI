from __future__ import annotations

import logging
import os
import time
from typing import Iterable

from sqlalchemy import select

from app.core.time import utc_now
from app.db.models.organization import Organization
from app.db.session import SessionLocal
from app.services.revenue_command_snapshot import run_snapshot_job

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 60 * 60 * 24  # daily


def _interval_seconds() -> int:
    raw = os.getenv("REVENUE_COMMAND_SNAPSHOT_INTERVAL_SECONDS", "").strip()
    try:
        value = int(raw)
        if value > 0:
            return value
    except Exception:
        pass
    return DEFAULT_INTERVAL_SECONDS


def _org_ids(db) -> Iterable[str]:
    return db.execute(select(Organization.id).order_by(Organization.created_at.asc())).scalars().all()


def run_once() -> int:
    db = SessionLocal()
    processed = 0
    started_at = utc_now()
    try:
        for org_id in _org_ids(db):
            run_snapshot_job(db, org_id)
            processed += 1
    except Exception:
        logger.exception("revenue_command_snapshot_scheduler_error")
    finally:
        db.close()
    logger.info(
        "revenue_command_snapshot_run_complete",
        extra={"processed_orgs": processed, "started_at": started_at.isoformat(), "finished_at": utc_now().isoformat()},
    )
    return processed


def run_loop() -> None:
    interval = _interval_seconds()
    logger.info("revenue_command_snapshot_scheduler_start interval_seconds=%s", interval)
    while True:
        run_once()
        time.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_loop()
