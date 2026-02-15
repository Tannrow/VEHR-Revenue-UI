#!/usr/bin/env python
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.bi import PowerBIClient, PowerBIServiceError  # noqa: E402

DEFAULT_RLS_ROLE = "TenantRLS"


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is not configured")
    return value


def main() -> int:
    try:
        workspace_id = _required_env("PBI_WORKSPACE_ID")
        report_id = _required_env("PBI_REPORT_ID_CHART_AUDIT")
        dataset_id = _required_env("PBI_DATASET_ID_CHART_AUDIT")
        rls_role = os.getenv("PBI_RLS_ROLE", DEFAULT_RLS_ROLE).strip() or DEFAULT_RLS_ROLE
    except ValueError as exc:
        print(f"success=False status=500 detail={exc}", file=sys.stderr)
        return 1

    try:
        client = PowerBIClient.from_env()
        access_token = client.get_access_token()
        report = client.get_report(
            workspace_id=workspace_id,
            report_id=report_id,
            access_token=access_token,
        )
        embed_token = client.generate_report_embed_token(
            workspace_id=workspace_id,
            report_id=report.id,
            dataset_id=dataset_id,
            username="1",
            rls_role=rls_role,
            access_token=access_token,
        )
    except PowerBIServiceError as exc:
        print(f"success=False status={exc.status_code} detail={exc.detail}", file=sys.stderr)
        return 1

    print(f"success=True status=200 reportId={report.id} expiresOn={embed_token.expires_on}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
