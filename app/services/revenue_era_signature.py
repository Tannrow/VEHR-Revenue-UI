from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.revenue_era import RevenueEraClaimLine, RevenueEraWorkItem


def _hash_rows(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_era_signature(db: Session, era_file_id: str) -> dict[str, Any]:
    claim_rows = (
        db.execute(
            select(RevenueEraClaimLine)
            .where(RevenueEraClaimLine.era_file_id == era_file_id)
            .order_by(RevenueEraClaimLine.line_index.asc(), RevenueEraClaimLine.id.asc())
        )
        .scalars()
        .all()
    )
    work_rows = (
        db.execute(
            select(RevenueEraWorkItem)
            .where(RevenueEraWorkItem.era_file_id == era_file_id)
            .order_by(RevenueEraWorkItem.claim_ref.asc(), RevenueEraWorkItem.id.asc())
        )
        .scalars()
        .all()
    )

    canonical_claims = [
        {
            "line_index": row.line_index,
            "claim_ref": row.claim_ref,
            "service_date": row.service_date.isoformat() if row.service_date else None,
            "proc_code": row.proc_code,
            "charge_cents": row.charge_cents,
            "allowed_cents": row.allowed_cents,
            "paid_cents": row.paid_cents,
            "adjustments_json": row.adjustments_json,
            "match_status": row.match_status,
        }
        for row in claim_rows
    ]
    canonical_work_items = [
        {
            "type": row.type,
            "dollars_cents": row.dollars_cents,
            "payer_name": row.payer_name,
            "claim_ref": row.claim_ref,
            "status": row.status,
        }
        for row in work_rows
    ]

    totals_cents = sum((row.dollars_cents or 0) for row in work_rows)
    claim_lines_hash = _hash_rows(canonical_claims)
    work_items_hash = _hash_rows(canonical_work_items)
    aggregate_hash = hashlib.sha256(
        json.dumps(
            {
                "claim_lines_count": len(canonical_claims),
                "work_items_count": len(canonical_work_items),
                "totals_cents": totals_cents,
                "claim_lines_hash": claim_lines_hash,
                "work_items_hash": work_items_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "claim_lines_count": len(canonical_claims),
        "work_items_count": len(canonical_work_items),
        "totals_cents": totals_cents,
        "claim_lines_hash": claim_lines_hash,
        "work_items_hash": work_items_hash,
        "aggregate_hash": aggregate_hash,
    }
