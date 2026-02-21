from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="era-ops", description="ERA operations CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    upload = sub.add_parser("upload", help="Upload an ERA PDF")
    upload.add_argument("--file", required=True, help="Path to ERA PDF")
    upload.add_argument("--base-url", default="http://127.0.0.1:8000")
    upload.add_argument("--token", help="Bearer token (or set VEHR_BEARER_TOKEN)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
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
