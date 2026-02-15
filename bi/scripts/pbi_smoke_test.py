#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from app.db.models.bi_report import BIReport  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.bi import PowerBIClient, PowerBIServiceError  # noqa: E402

DEFAULT_RLS_ROLE = "TenantRLS"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke test embed token generation for a BI report key using a fake org identity.",
    )
    parser.add_argument(
        "--report-key",
        default="chart_audit",
        help="Report key from bi_reports table (default: chart_audit).",
    )
    parser.add_argument(
        "--org-id",
        default="1",
        help="Fake org identity used for USERNAME() RLS validation (default: 1).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_key = args.report_key.strip().lower()
    fake_org_id = args.org_id.strip() or "1"
    db = SessionLocal()

    try:
        row = db.execute(
            select(BIReport).where(
                BIReport.report_key == report_key,
                BIReport.is_enabled.is_(True),
            )
        ).scalar_one_or_none()
        if row is None:
            print(
                f"success=False status=404 detail=Enabled report key not found: {report_key}",
                file=sys.stderr,
            )
            return 1

        client = PowerBIClient.from_env()
        access_token = client.get_access_token()
        report = client.get_report(
            workspace_id=row.workspace_id,
            report_id=row.report_id,
            access_token=access_token,
        )
        embed_token = client.generate_report_embed_token(
            workspace_id=row.workspace_id,
            report_id=report.id,
            dataset_id=row.dataset_id,
            username=fake_org_id,
            rls_role=row.rls_role or DEFAULT_RLS_ROLE,
            access_token=access_token,
        )
    except PowerBIServiceError as exc:
        print(f"success=False status={exc.status_code} detail={exc.detail}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"success=True status=200 reportId={report.id} expiresOn={embed_token.expires_on}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
