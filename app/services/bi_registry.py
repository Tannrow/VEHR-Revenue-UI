from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.bi_report import BIReport

CHART_AUDIT_REPORT_KEY = "chart_audit"
CHART_AUDIT_NAME = "Chart Audit"
CHART_AUDIT_WORKSPACE_ID = "b64502e3-dc61-413b-9666-96e106133208"
CHART_AUDIT_REPORT_ID = "654a0794-ab05-43f4-ac9b-9a968203a361"
CHART_AUDIT_DATASET_ID = "3737a027-ff43-477c-970a-54aed93cc8ed"
DEFAULT_BI_RLS_ROLE = "TenantRLS"

REPORT_DEFINITIONS = (
    {
        "report_key": "chart_audit",
        "name": "Chart Audit",
        "fallback_workspace_id": CHART_AUDIT_WORKSPACE_ID,
        "fallback_report_id": CHART_AUDIT_REPORT_ID,
        "fallback_dataset_id": CHART_AUDIT_DATASET_ID,
    },
    {
        "report_key": "executive_overview",
        "name": "Executive Overview",
    },
    {
        "report_key": "revenue_cycle",
        "name": "Revenue Cycle",
    },
    {
        "report_key": "clinical_delivery",
        "name": "Clinical Delivery",
    },
    {
        "report_key": "compliance_risk",
        "name": "Compliance & Risk",
    },
    # Backward-compatible key (older naming in earlier builds).
    {
        "report_key": "exec_overview",
        "name": "Executive Overview",
    },
)


def default_workspace_id() -> str:
    return os.getenv("PBI_DEFAULT_WORKSPACE_ID", "").strip() or CHART_AUDIT_WORKSPACE_ID


def default_rls_role() -> str:
    return os.getenv("PBI_RLS_ROLE", DEFAULT_BI_RLS_ROLE).strip() or DEFAULT_BI_RLS_ROLE


def _env_name(prefix: str, report_key: str) -> str:
    normalized = report_key.strip().upper()
    return f"{prefix}_{normalized}"


def _read_env_or_fallback(
    *,
    report_key: str,
    env_prefix: str,
    fallback_value: str = "",
) -> str:
    env_name = _env_name(env_prefix, report_key)
    value = os.getenv(env_name, "").strip()
    if value:
        return value
    return fallback_value.strip()


def upsert_bi_report(
    db: Session,
    *,
    report_key: str,
    name: str | None,
    workspace_id: str,
    report_id: str,
    dataset_id: str,
    rls_role: str,
    is_enabled: bool = True,
) -> BIReport:
    normalized_key = report_key.strip().lower()
    row = db.execute(
        select(BIReport).where(BIReport.report_key == normalized_key)
    ).scalar_one_or_none()
    if row is None:
        row = BIReport(
            report_key=normalized_key,
            name=name.strip() if isinstance(name, str) and name.strip() else None,
            workspace_id=workspace_id.strip(),
            report_id=report_id.strip(),
            dataset_id=dataset_id.strip(),
            rls_role=rls_role.strip(),
            is_enabled=bool(is_enabled),
        )
        db.add(row)
    else:
        row.name = name.strip() if isinstance(name, str) and name.strip() else row.name
        row.workspace_id = workspace_id.strip()
        row.report_id = report_id.strip()
        row.dataset_id = dataset_id.strip()
        row.rls_role = rls_role.strip()
        row.is_enabled = bool(is_enabled)
        db.add(row)

    db.commit()
    db.refresh(row)
    return row


def seed_bi_reports(db: Session) -> list[BIReport]:
    seeded: list[BIReport] = []
    for definition in REPORT_DEFINITIONS:
        report_key = definition["report_key"]
        workspace_id = _read_env_or_fallback(
            report_key=report_key,
            env_prefix="PBI_WORKSPACE_ID",
            fallback_value=definition.get("fallback_workspace_id", "") or default_workspace_id(),
        ) or default_workspace_id()
        report_id = _read_env_or_fallback(
            report_key=report_key,
            env_prefix="PBI_REPORT_ID",
            fallback_value=definition.get("fallback_report_id", ""),
        )
        dataset_id = _read_env_or_fallback(
            report_key=report_key,
            env_prefix="PBI_DATASET_ID",
            fallback_value=definition.get("fallback_dataset_id", ""),
        )

        if not report_id or not dataset_id:
            continue

        seeded.append(
            upsert_bi_report(
                db,
                report_key=report_key,
                name=definition["name"],
                workspace_id=workspace_id,
                report_id=report_id,
                dataset_id=dataset_id,
                rls_role=default_rls_role(),
                is_enabled=True,
            )
        )
    return seeded
