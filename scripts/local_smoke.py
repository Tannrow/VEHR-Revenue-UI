from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import uuid
from pathlib import Path
from urllib import error, request


def _http_json(
    method: str,
    url: str,
    *,
    payload: dict | None = None,
    token: str | None = None,
    content_type: str = "application/json",
) -> tuple[int, dict]:
    body: bytes | None = None
    req = request.Request(url, method=method.upper())
    req.add_header("Accept", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req.add_header("Content-Type", content_type)
    try:
        with request.urlopen(req, data=body) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {}
        return exc.code, parsed


def _multipart_upload(url: str, *, file_path: Path, token: str) -> tuple[int, dict]:
    boundary = f"----vehr-local-smoke-{uuid.uuid4().hex}"
    ctype = mimetypes.guess_type(str(file_path))[0] or "application/pdf"
    file_bytes = file_path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files"; filename="{file_path.name}"\r\n'
        f"Content-Type: {ctype}\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = request.Request(url, data=body, method="POST")
    req.add_header("Accept", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with request.urlopen(req) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {}
        return exc.code, parsed


def _detail(payload: dict) -> dict:
    detail = payload.get("detail")
    return detail if isinstance(detail, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Revenue OS smoke path (bootstrap -> login -> upload -> process -> debug)")
    parser.add_argument("--file", required=True, help="Absolute path to ERA PDF")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--org-name", default="Local Revenue OS")
    parser.add_argument("--email", default="admin@example.com")
    parser.add_argument("--password", default="ChangeMeNow!")
    args = parser.parse_args()

    file_path = Path(args.file).expanduser().resolve()
    if not file_path.exists():
        print(f"error=file_not_found path={file_path}", file=sys.stderr)
        return 1

    base_url = args.base_url.rstrip("/")

    if os.getenv("BOOTSTRAP_ENABLED") == "1":
        bootstrap_status, bootstrap_payload = _http_json(
            "POST",
            f"{base_url}/api/v1/bootstrap",
            payload={
                "organization_name": args.org_name,
                "admin_email": args.email,
                "admin_password": args.password,
                "admin_name": "Local Smoke Admin",
            },
        )
        if bootstrap_status not in {200, 201}:
            print(f"stage=bootstrap status={bootstrap_status}", file=sys.stderr)
            return 1
        print(
            "bootstrap"
            f" organization_id={bootstrap_payload.get('organization_id')}"
            f" admin_user_id={bootstrap_payload.get('admin_user_id')}"
        )

    login_status, login_payload = _http_json(
        "POST",
        f"{base_url}/api/v1/auth/login",
        payload={"email": args.email, "password": args.password},
    )
    if login_status != 200:
        print(f"stage=login status={login_status}", file=sys.stderr)
        return 1
    token = login_payload.get("access_token")
    if not isinstance(token, str) or not token:
        print("stage=login status=200 error=missing_access_token", file=sys.stderr)
        return 1
    print(
        "login"
        f" organization_id={login_payload.get('organization_id')}"
        f" user_id={login_payload.get('user_id')}"
    )

    upload_status, upload_payload = _multipart_upload(
        f"{base_url}/api/v1/revenue/era-pdfs/upload",
        file_path=file_path,
        token=token,
    )
    if upload_status != 200 or not isinstance(upload_payload, list) or not upload_payload:
        print(f"stage=upload status={upload_status}", file=sys.stderr)
        return 1
    era_row = upload_payload[0] if isinstance(upload_payload[0], dict) else {}
    era_file_id = era_row.get("id")
    if not isinstance(era_file_id, str) or not era_file_id:
        print("stage=upload status=200 error=missing_era_file_id", file=sys.stderr)
        return 1
    print(f"upload era_file_id={era_file_id} status={era_row.get('status')}")

    process_status, process_payload = _http_json(
        "POST",
        f"{base_url}/api/v1/revenue/era-pdfs/{era_file_id}/process",
        token=token,
    )
    if process_status == 502:
        error_code = process_payload.get("error_code")
        stage = process_payload.get("stage")
        print(f"process status=502 stage={stage} error_code={error_code}", file=sys.stderr)
        return 2
    if process_status == 409:
        detail = _detail(process_payload)
        print(
            "process status=409"
            f" error_code={detail.get('error_code')}"
            f" current_status={detail.get('current_status')}"
        )
        return 3
    if process_status != 200:
        detail = _detail(process_payload)
        print(
            "process"
            f" status={process_status}"
            f" error_code={detail.get('error_code') or process_payload.get('error_code')}",
            file=sys.stderr,
        )
        return 1
    print(f"process status={process_payload.get('status')} era_file_id={process_payload.get('id')}")

    debug_status, debug_payload = _http_json(
        "GET",
        f"{base_url}/api/v1/revenue/era-pdfs/{era_file_id}/debug",
        token=token,
    )
    if debug_status != 200:
        print(f"stage=debug status={debug_status}", file=sys.stderr)
        return 1

    era_file = debug_payload.get("era_file") if isinstance(debug_payload, dict) else {}
    if (
        "extracted_json" in debug_payload
        or "structured_json" in debug_payload
        or (isinstance(era_file, dict) and ("extracted_json" in era_file or "structured_json" in era_file))
    ):
        print("stage=debug error=unsafe_keys_present", file=sys.stderr)
        return 1

    row_counts = debug_payload.get("row_counts") if isinstance(debug_payload, dict) else {}
    logs = debug_payload.get("latest_processing_logs") if isinstance(debug_payload, dict) else []
    latest_stages = [entry.get("stage") for entry in logs if isinstance(entry, dict) and isinstance(entry.get("stage"), str)][
        :5
    ]
    if isinstance(row_counts, dict):
        counts_text = ",".join(
            f"{key}={row_counts.get(key)}"
            for key in ("extract_results", "structured_results", "claim_lines", "work_items", "validation_reports")
        )
    else:
        counts_text = ""
    print(f"debug status={era_file.get('status') if isinstance(era_file, dict) else None} row_counts={counts_text} latest_stages={latest_stages}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
