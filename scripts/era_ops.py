from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
import uuid
from pathlib import Path
from urllib import error, request


def _multipart_body(file_path: Path) -> tuple[bytes, str]:
    boundary = f"----vehr-era-ops-{uuid.uuid4().hex}"
    ctype = mimetypes.guess_type(str(file_path))[0] or "application/pdf"
    file_bytes = file_path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files"; filename="{file_path.name}"\r\n'
        f"Content-Type: {ctype}\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return body, boundary


def _http_json(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: dict[str, object] | None = None,
) -> tuple[int, object]:
    body: bytes | None = None
    req = request.Request(url, method=method.upper())
    req.add_header("Accept", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req.add_header("Content-Type", "application/json")
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


def _upload(base_url: str, *, file_path: Path, token: str) -> tuple[int, object]:
    body, boundary = _multipart_body(file_path)
    req = request.Request(
        f"{base_url.rstrip('/')}/api/v1/revenue/era-pdfs/upload",
        data=body,
        method="POST",
    )
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Accept", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with request.urlopen(req) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"detail": "invalid_json_response"}
        return exc.code, payload


def _login(base_url: str, *, email: str, password: str) -> tuple[int, str | None, object]:
    status, payload = _http_json(
        "POST",
        f"{base_url.rstrip('/')}/api/v1/auth/login",
        payload={"email": email, "password": password},
    )
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if isinstance(token, str) and token:
        return status, token, payload
    return status, None, payload


def _extract_error_fields(payload: object) -> tuple[str | None, str | None, str | None]:
    source = payload if isinstance(payload, dict) else {}
    detail = source.get("detail") if isinstance(source, dict) else None
    if isinstance(detail, dict):
        source = detail
    stage = source.get("stage") if isinstance(source, dict) else None
    error_code = source.get("error_code") if isinstance(source, dict) else None
    request_id = source.get("request_id") if isinstance(source, dict) else None
    safe_stage = stage if isinstance(stage, str) and stage else None
    safe_error_code = error_code if isinstance(error_code, str) and error_code else None
    safe_request_id = request_id if isinstance(request_id, str) and request_id else None
    return safe_stage, safe_error_code, safe_request_id


def _process(base_url: str, *, era_file_id: str, token: str) -> tuple[int, object]:
    return _http_json("POST", f"{base_url.rstrip('/')}/api/v1/revenue/era-pdfs/{era_file_id}/process", token=token)


def _iter_pdf_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".pdf")


def _ingest_file(base_url: str, *, file_path: Path, token: str) -> bool:
    upload_status, upload_payload = _upload(base_url, file_path=file_path, token=token)
    if upload_status != 200 or not isinstance(upload_payload, list) or not upload_payload:
        print(f"file={file_path.name} stage=upload status={upload_status}", file=sys.stderr)
        return False
    first = upload_payload[0] if isinstance(upload_payload[0], dict) else {}
    era_file_id = first.get("id")
    if not isinstance(era_file_id, str) or not era_file_id:
        print(f"file={file_path.name} stage=upload status=200 error_code=MISSING_ERA_FILE_ID", file=sys.stderr)
        return False

    process_status, process_payload = _process(base_url, era_file_id=era_file_id, token=token)
    if process_status == 200 and isinstance(process_payload, dict):
        print(
            f"file={file_path.name} era_file_id={era_file_id} upload_status={first.get('status')} process_status={process_payload.get('status')}"
        )
        return True

    stage, error_code, request_id = _extract_error_fields(process_payload)
    print(
        f"file={file_path.name} era_file_id={era_file_id} stage={stage or 'process'}"
        f" status={process_status} error_code={error_code or 'UNKNOWN'} request_id={request_id or '-'}",
        file=sys.stderr,
    )
    return False


def _run_ingest(base_url: str, *, directory: Path, token: str) -> tuple[int, int]:
    files = _iter_pdf_files(directory)
    success_count = 0
    failure_count = 0
    for file_path in files:
        if _ingest_file(base_url, file_path=file_path, token=token):
            success_count += 1
        else:
            failure_count += 1
    return success_count, failure_count


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="era-ops", description="ERA operations CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="Login and verify credentials")
    login.add_argument("--base-url", default="http://127.0.0.1:8000")
    login.add_argument("--email", default=os.getenv("VEHR_EMAIL", "admin@example.com"))
    login.add_argument("--password", default=os.getenv("VEHR_PASSWORD", "ChangeMeNow!"))

    ingest = sub.add_parser("ingest", help="Bulk ingest ERA PDFs from a directory")
    ingest.add_argument("--dir", required=True, help="Directory containing ERA PDFs")
    ingest.add_argument("--base-url", default="http://127.0.0.1:8000")
    ingest.add_argument("--email", default=os.getenv("VEHR_EMAIL", "admin@example.com"))
    ingest.add_argument("--password", default=os.getenv("VEHR_PASSWORD", "ChangeMeNow!"))
    ingest.add_argument("--watch", action="store_true", help="Watch folder for new PDFs")
    ingest.add_argument("--poll-seconds", type=float, default=2.0)

    upload = sub.add_parser("upload", help="Upload an ERA PDF")
    upload.add_argument("--file", required=True, help="Path to ERA PDF")
    upload.add_argument("--base-url", default="http://127.0.0.1:8000")
    upload.add_argument("--token", help="Bearer token (or set VEHR_BEARER_TOKEN)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "login":
        status, token, payload = _login(args.base_url, email=args.email, password=args.password)
        if status != 200 or not token:
            print(f"stage=login status={status}", file=sys.stderr)
            return 1
        organization_id = payload.get("organization_id") if isinstance(payload, dict) else None
        user_id = payload.get("user_id") if isinstance(payload, dict) else None
        print(f"login status=200 organization_id={organization_id} user_id={user_id}")
        return 0

    if args.command == "ingest":
        directory = Path(args.dir).expanduser().resolve()
        if not directory.exists() or not directory.is_dir():
            print(f"error=invalid_dir path={directory}", file=sys.stderr)
            return 1
        status, token, _ = _login(args.base_url, email=args.email, password=args.password)
        if status != 200 or not token:
            print(f"stage=login status={status}", file=sys.stderr)
            return 1
        if not args.watch:
            success_count, failure_count = _run_ingest(args.base_url, directory=directory, token=token)
            print(f"summary success={success_count} failure={failure_count}")
            return 0 if failure_count == 0 else 1

        seen = set(_iter_pdf_files(directory))
        print(f"watching dir={directory} poll_seconds={args.poll_seconds}")
        while True:
            current = _iter_pdf_files(directory)
            new_files = [path for path in current if path not in seen]
            for file_path in new_files:
                _ingest_file(args.base_url, file_path=file_path, token=token)
                seen.add(file_path)
            time.sleep(max(args.poll_seconds, 0.2))

    if args.command != "upload":
        return 1

    file_path = Path(args.file).expanduser().resolve()
    if not file_path.exists():
        print(f"error=file_not_found path={file_path}", file=sys.stderr)
        return 1

    token = (args.token or os.getenv("VEHR_BEARER_TOKEN", "")).strip()
    if not token:
        print("error=missing_token", file=sys.stderr)
        return 1

    status, payload = _upload(args.base_url, file_path=file_path, token=token)
    if status != 200 or not isinstance(payload, list) or not payload:
        print(f"stage=upload status={status}", file=sys.stderr)
        return 1

    first = payload[0] if isinstance(payload[0], dict) else {}
    era_file_id = first.get("id")
    if not isinstance(era_file_id, str) or not era_file_id:
        print("stage=upload status=200 error=missing_era_file_id", file=sys.stderr)
        return 1

    print(f"upload era_file_id={era_file_id} status={first.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
