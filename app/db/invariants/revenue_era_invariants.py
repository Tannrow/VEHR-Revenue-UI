from __future__ import annotations

from typing import Any

from sqlalchemy import and_, distinct, func, select
from sqlalchemy.orm import Session

from app.db.models.revenue_era import (
    RevenueEraClaimLine,
    RevenueEraExtractResult,
    RevenueEraFile,
    RevenueEraStructuredResult,
    RevenueEraWorkItem,
)
from app.services.revenue_era import STATUS_COMPLETE, STATUS_ERROR


def _failure(name: str, count: int, sample_ids: list[str] | None = None) -> dict[str, Any]:
    return {"name": name, "count": int(count), "sample_ids": sample_ids or []}


def run_revenue_era_invariants(
    db: Session,
    organization_id: str,
    era_file_ids: list[str] | None = None,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    file_scope = and_(RevenueEraFile.organization_id == organization_id)
    if era_file_ids:
        file_scope = and_(file_scope, RevenueEraFile.id.in_(era_file_ids))

    files = db.execute(select(RevenueEraFile.id).where(file_scope)).scalars().all()
    if not files:
        return {"pass": True, "failures": []}

    scoped_ids = set(files)

    def _add_if_any(name: str, ids: list[str]) -> None:
        if ids:
            failures.append(_failure(name, len(ids), ids[:10]))

    extract_orphans = db.execute(
        select(RevenueEraExtractResult.era_file_id).outerjoin(
            RevenueEraFile, RevenueEraFile.id == RevenueEraExtractResult.era_file_id
        ).where(
            RevenueEraExtractResult.era_file_id.in_(scoped_ids),
            RevenueEraFile.id.is_(None),
        )
    ).scalars().all()
    _add_if_any("orphan_extract_rows", list(dict.fromkeys(extract_orphans)))

    structured_orphans = db.execute(
        select(RevenueEraStructuredResult.era_file_id).outerjoin(
            RevenueEraFile, RevenueEraFile.id == RevenueEraStructuredResult.era_file_id
        ).where(
            RevenueEraStructuredResult.era_file_id.in_(scoped_ids),
            RevenueEraFile.id.is_(None),
        )
    ).scalars().all()
    _add_if_any("orphan_structured_rows", list(dict.fromkeys(structured_orphans)))

    claim_orphans = db.execute(
        select(RevenueEraClaimLine.era_file_id).outerjoin(
            RevenueEraFile, RevenueEraFile.id == RevenueEraClaimLine.era_file_id
        ).where(
            RevenueEraClaimLine.era_file_id.in_(scoped_ids),
            RevenueEraFile.id.is_(None),
        )
    ).scalars().all()
    _add_if_any("orphan_claim_line_rows", list(dict.fromkeys(claim_orphans)))

    work_orphans = db.execute(
        select(RevenueEraWorkItem.era_file_id).outerjoin(
            RevenueEraFile, RevenueEraFile.id == RevenueEraWorkItem.era_file_id
        ).where(
            RevenueEraWorkItem.era_file_id.in_(scoped_ids),
            RevenueEraFile.id.is_(None),
        )
    ).scalars().all()
    _add_if_any("orphan_work_item_rows", list(dict.fromkeys(work_orphans)))

    complete_rows = db.execute(
        select(RevenueEraFile).where(
            RevenueEraFile.id.in_(scoped_ids),
            RevenueEraFile.status == STATUS_COMPLETE,
        )
    ).scalars().all()
    complete_failures: list[str] = []
    for row in complete_rows:
        structured_count = db.execute(
            select(func.count())
            .select_from(RevenueEraStructuredResult)
            .where(RevenueEraStructuredResult.era_file_id == row.id)
        ).scalar_one()
        claim_count = db.execute(
            select(func.count()).select_from(RevenueEraClaimLine).where(RevenueEraClaimLine.era_file_id == row.id)
        ).scalar_one()
        if (row.current_stage or "").lower() != "complete":
            complete_failures.append(row.id)
        elif row.stage_completed_at is None:
            complete_failures.append(row.id)
        elif structured_count < 1:
            complete_failures.append(row.id)
        elif claim_count < 1:
            complete_failures.append(row.id)
    _add_if_any("complete_state_integrity", complete_failures)

    failed_rows = db.execute(
        select(RevenueEraFile.id).where(
            RevenueEraFile.id.in_(scoped_ids),
            RevenueEraFile.status == STATUS_ERROR,
        )
    ).scalars().all()
    failed_partial: list[str] = []
    for era_file_id in failed_rows:
        claim_count = db.execute(
            select(func.count()).select_from(RevenueEraClaimLine).where(RevenueEraClaimLine.era_file_id == era_file_id)
        ).scalar_one()
        work_count = db.execute(
            select(func.count()).select_from(RevenueEraWorkItem).where(RevenueEraWorkItem.era_file_id == era_file_id)
        ).scalar_one()
        if claim_count > 0 or work_count > 0:
            failed_partial.append(era_file_id)
    _add_if_any("failed_state_partial_rows", failed_partial)

    duplicate_line_groups = db.execute(
        select(RevenueEraClaimLine.era_file_id)
        .where(RevenueEraClaimLine.era_file_id.in_(scoped_ids))
        .group_by(RevenueEraClaimLine.era_file_id, RevenueEraClaimLine.line_index)
        .having(func.count() > 1)
    ).scalars().all()
    _add_if_any("duplicate_claim_line_indexes", list(dict.fromkeys(duplicate_line_groups)))

    duplicate_work_groups = db.execute(
        select(RevenueEraWorkItem.era_file_id)
        .where(RevenueEraWorkItem.era_file_id.in_(scoped_ids))
        .group_by(RevenueEraWorkItem.era_file_id, RevenueEraWorkItem.claim_ref)
        .having(func.count() > 1)
    ).scalars().all()
    _add_if_any("duplicate_work_item_claim_refs", list(dict.fromkeys(duplicate_work_groups)))

    complete_with_error = db.execute(
        select(RevenueEraFile.id).where(
            RevenueEraFile.id.in_(scoped_ids),
            RevenueEraFile.status == STATUS_COMPLETE,
            RevenueEraFile.last_error_stage.is_not(None),
        )
    ).scalars().all()
    _add_if_any("complete_with_last_error_stage", complete_with_error)

    terminal_with_open_stage = db.execute(
        select(RevenueEraFile.id).where(
            RevenueEraFile.id.in_(scoped_ids),
            RevenueEraFile.status.in_([STATUS_COMPLETE, STATUS_ERROR]),
            RevenueEraFile.stage_started_at.is_not(None),
            RevenueEraFile.stage_completed_at.is_(None),
        )
    ).scalars().all()
    _add_if_any("terminal_state_missing_stage_completed_at", terminal_with_open_stage)

    scoped_count = db.execute(
        select(func.count(distinct(RevenueEraFile.id))).where(RevenueEraFile.id.in_(scoped_ids))
    ).scalar_one()
    if scoped_count != len(scoped_ids):
        failures.append(_failure("scoped_file_count_mismatch", abs(scoped_count - len(scoped_ids))))

    return {"pass": len(failures) == 0, "failures": failures}
