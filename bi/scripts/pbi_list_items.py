#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.bi import PowerBIClient, PowerBIServiceError  # noqa: E402


def _workspace_name(row: dict[str, Any]) -> str:
    return str(row.get("name", "")).strip() or "(unnamed workspace)"


def _workspace_id(row: dict[str, Any]) -> str:
    return str(row.get("id", "")).strip()


def _print_workspaces(workspaces: list[dict[str, Any]]) -> None:
    print("Accessible workspaces:")
    if not workspaces:
        print("- none")
        return
    for row in workspaces:
        print(f"- {_workspace_name(row)} [{_workspace_id(row)}]")


def _resolve_workspace_id(
    *,
    workspaces: list[dict[str, Any]],
    workspace_id: str | None,
    workspace_name_contains: str | None,
) -> str:
    if workspace_id:
        return workspace_id

    if workspace_name_contains:
        needle = workspace_name_contains.strip().lower()
        matched = [
            row for row in workspaces if needle in _workspace_name(row).lower() and _workspace_id(row)
        ]
        if len(matched) == 1:
            return _workspace_id(matched[0])
        if len(matched) > 1:
            raise ValueError(
                "More than one workspace matched --workspace-name-contains; provide --workspace-id."
            )
        raise ValueError("No workspace matched --workspace-name-contains.")

    valid_ids = [_workspace_id(row) for row in workspaces if _workspace_id(row)]
    if len(valid_ids) == 1:
        return valid_ids[0]
    raise ValueError(
        "Workspace id is required. Set PBI_DEFAULT_WORKSPACE_ID or pass --workspace-id. "
        "You can also use --workspace-name-contains."
    )


def _print_reports(reports: list[dict[str, Any]]) -> None:
    print("Reports:")
    if not reports:
        print("- none")
        return
    for row in reports:
        name = str(row.get("name", "")).strip() or "(unnamed report)"
        report_id = str(row.get("id", "")).strip() or "(missing id)"
        embed_url = str(row.get("embedUrl", "")).strip() or "(missing embedUrl)"
        print(f"- name={name}")
        print(f"  id={report_id}")
        print(f"  embedUrl={embed_url}")


def _print_datasets(datasets: list[dict[str, Any]]) -> None:
    print("Datasets:")
    if not datasets:
        print("- none")
        return
    for row in datasets:
        name = str(row.get("name", "")).strip() or "(unnamed dataset)"
        dataset_id = str(row.get("id", "")).strip() or "(missing id)"
        print(f"- name={name}")
        print(f"  id={dataset_id}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List Power BI/Fabric workspaces, reports, and datasets available to the service principal.",
    )
    parser.add_argument(
        "--workspace-id",
        default=(
            os.getenv("PBI_WORKSPACE_ID", "").strip()
            or os.getenv("PBI_DEFAULT_WORKSPACE_ID", "").strip()
            or None
        ),
        help="Workspace ID. Defaults to PBI_WORKSPACE_ID or PBI_DEFAULT_WORKSPACE_ID if set.",
    )
    parser.add_argument(
        "--workspace-name-contains",
        default=None,
        help='Select a workspace by case-insensitive name match (example: "360E Analytics").',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        client = PowerBIClient.from_env()
        access_token = client.get_access_token()
        workspaces = client.list_workspaces(access_token=access_token)
    except PowerBIServiceError as exc:
        print(f"[ERROR] status={exc.status_code} detail={exc.detail}", file=sys.stderr)
        return 1

    _print_workspaces(workspaces)

    try:
        workspace_id = _resolve_workspace_id(
            workspaces=workspaces,
            workspace_id=args.workspace_id,
            workspace_name_contains=args.workspace_name_contains,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    print("")
    print(f"workspaceId={workspace_id}")

    try:
        reports = client.list_reports(workspace_id=workspace_id, access_token=access_token)
        datasets = client.list_datasets(workspace_id=workspace_id, access_token=access_token)
    except PowerBIServiceError as exc:
        print(f"[ERROR] status={exc.status_code} detail={exc.detail}", file=sys.stderr)
        return 1

    _print_reports(reports)
    _print_datasets(datasets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
