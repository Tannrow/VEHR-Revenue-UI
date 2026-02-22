from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import multiprocessing
import os
import platform
import resource
import statistics
import sys
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, TimeoutError as CFTimeoutError
from pathlib import Path
from time import perf_counter
from urllib import error, request
from urllib.parse import urlparse

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.invariants.revenue_era_invariants import run_revenue_era_invariants
from app.db.models.revenue_era import RevenueEraFile


def _percentile(values: list[int], pct: int) -> int:
    if not values:
        return 0
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * (pct / 100)
    lower = int(rank)
    upper = min(lower + 1, len(values) - 1)
    frac = rank - lower
    ordered = sorted(values)
    return int(ordered[lower] + (ordered[upper] - ordered[lower]) * frac)


def _rss_mb() -> float:
    value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if platform.system() == "Darwin":
        return value / (1024.0 * 1024.0)
    return value / 1024.0


def _valid_base_url(base_url: str) -> bool:
    parsed = urlparse(base_url.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _json_request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    body: bytes | None = None,
    content_type: str | None = None,
) -> tuple[int, object]:
    req = request.Request(url, method=method.upper(), data=body)
    req.add_header("Accept", "application/json")
    req.add_header("x-request-id", f"load-{uuid.uuid4().hex}")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if content_type:
        req.add_header("Content-Type", content_type)
    try:
        with request.urlopen(req) as response:  # noqa: S310
            payload_raw = response.read().decode("utf-8")
            payload = json.loads(payload_raw) if payload_raw else {}
            return response.status, payload
    except error.HTTPError as exc:
        payload_raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(payload_raw) if payload_raw else {}
        except json.JSONDecodeError:
            payload = {"error": "invalid_json_response"}
        return exc.code, payload


def _login(base_url: str, *, email: str, password: str) -> tuple[str | None, str | None]:
    payload = json.dumps({"email": email, "password": password}).encode("utf-8")
    status, data = _json_request(
        "POST",
        f"{base_url.rstrip('/')}/api/v1/auth/login",
        body=payload,
        content_type="application/json",
    )
    if status != 200 or not isinstance(data, dict):
        return None, None
    token = data.get("access_token")
    org_id = data.get("organization_id")
    safe_token = token if isinstance(token, str) and token else None
    safe_org_id = org_id if isinstance(org_id, str) and org_id else None
    return safe_token, safe_org_id


def _multipart_pdf(file_path: Path) -> tuple[bytes, str]:
    boundary = f"----vehr-era-load-{uuid.uuid4().hex}"
    ctype = mimetypes.guess_type(str(file_path))[0] or "application/pdf"
    content = file_path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files"; filename="{file_path.name}"\r\n'
        f"Content-Type: {ctype}\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return body, boundary


def _extract_stage_durations(logs: list[dict]) -> dict[str, int]:
    stage_durations: dict[str, int] = {}
    for row in logs:
        stage = row.get("stage")
        message = row.get("message")
        if not isinstance(stage, str) or not isinstance(message, str):
            continue
        for part in message.split(";"):
            key, _, value = part.strip().partition("=")
            if key == "duration_ms" and value.isdigit():
                stage_durations[stage.lower()] = int(value)
    return stage_durations


def _process_error_fields(payload: object) -> tuple[str, str]:
    if not isinstance(payload, dict):
        return "unknown_error", "-"
    request_id = payload.get("request_id") if isinstance(payload.get("request_id"), str) else "-"
    error_code = payload.get("error_code")
    if not isinstance(error_code, str):
        detail = payload.get("detail")
        if isinstance(detail, dict):
            code = detail.get("error_code")
            if isinstance(code, str):
                error_code = code
    if not isinstance(error_code, str):
        error_code = "unknown_error"
    return error_code, request_id


def _deterministic_signature(base_url: str, *, token: str, era_file_id: str) -> str | None:
    report_status, report_payload = _json_request(
        "GET",
        f"{base_url.rstrip('/')}/api/v1/era/{era_file_id}/report",
        token=token,
    )
    if report_status != 200 or not isinstance(report_payload, dict):
        return None
    allowed = {
        "claim_count",
        "line_count",
        "work_item_count",
        "total_paid_cents",
        "total_adjustment_cents",
        "total_patient_resp_cents",
        "net_cents",
        "reconciled",
        "declared_total_missing",
    }
    material = {key: report_payload.get(key) for key in sorted(allowed)}
    blob = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _find_existing_era_id(base_url: str, *, token: str, file_name: str) -> str | None:
    status, payload = _json_request("GET", f"{base_url.rstrip('/')}/api/v1/revenue/era-pdfs", token=token)
    if status != 200 or not isinstance(payload, list):
        return None
    for row in payload:
        if isinstance(row, dict) and row.get("file_name") == file_name and isinstance(row.get("id"), str):
            return row["id"]
    return None


def _run_one(base_url: str, *, token: str, pdf_path: Path) -> dict:
    started = perf_counter()
    body, boundary = _multipart_pdf(pdf_path)
    upload_status, upload_payload = _json_request(
        "POST",
        f"{base_url.rstrip('/')}/api/v1/revenue/era-pdfs/upload",
        token=token,
        body=body,
        content_type=f"multipart/form-data; boundary={boundary}",
    )
    era_file_id: str | None = None
    if upload_status == 200 and isinstance(upload_payload, list) and upload_payload and isinstance(upload_payload[0], dict):
        era_file_id = upload_payload[0].get("id") if isinstance(upload_payload[0].get("id"), str) else None
    elif upload_status == 409 and isinstance(upload_payload, dict) and upload_payload.get("detail") == "duplicate_upload":
        era_file_id = _find_existing_era_id(base_url, token=token, file_name=pdf_path.name)
    if not era_file_id:
        return {
            "ok": False,
            "error_code": "upload_failed",
            "request_id": "-",
            "duration_ms": int((perf_counter() - started) * 1000),
            "stage_durations": {},
            "rss_mb": round(_rss_mb(), 2),
            "source_file": pdf_path.name,
            "deterministic_hash": None,
        }

    process_started = perf_counter()
    process_status, process_payload = _json_request(
        "POST",
        f"{base_url.rstrip('/')}/api/v1/revenue/era-pdfs/{era_file_id}/process",
        token=token,
    )
    process_duration_ms = int((perf_counter() - process_started) * 1000)
    if process_status == 409 and isinstance(process_payload, dict):
        detail = process_payload.get("detail")
        if isinstance(detail, dict) and detail.get("error_code") == "ERA_ALREADY_COMPLETE":
            process_status = 200

    error_code, request_id = _process_error_fields(process_payload)
    debug_status, debug_payload = _json_request(
        "GET",
        f"{base_url.rstrip('/')}/api/v1/revenue/era-pdfs/{era_file_id}/debug",
        token=token,
    )
    latest_logs: list[dict] = []
    if debug_status == 200 and isinstance(debug_payload, dict):
        logs = debug_payload.get("latest_processing_logs")
        if isinstance(logs, list):
            latest_logs = [row for row in logs if isinstance(row, dict)]

    return {
        "ok": process_status == 200,
        "error_code": error_code,
        "request_id": request_id,
        "duration_ms": process_duration_ms,
        "stage_durations": _extract_stage_durations(latest_logs),
        "rss_mb": round(_rss_mb(), 2),
        "source_file": pdf_path.name,
        "deterministic_hash": _deterministic_signature(base_url, token=token, era_file_id=era_file_id),
    }


def _run_one_worker(args: tuple[str, str, str]) -> dict:
    base_url, token, pdf_path = args
    return _run_one(base_url, token=token, pdf_path=Path(pdf_path))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="load-test", description="ERA stress and concurrency runner")
    parser.add_argument("--dir", required=True, help="Directory of test PDF fixtures")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--email", default="admin@example.com")
    parser.add_argument("--password", default="ChangeMeNow!")
    parser.add_argument("--token", default="", help="Optional bearer token")
    parser.add_argument("--organization-id", default="", help="Organization id when token is supplied")
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--mode", choices=("threads", "processes"), default="processes")
    parser.add_argument("--job-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--memory-ceiling-mb", type=float, default=1024.0)
    return parser


def _run_invariants(*, organization_id: str) -> dict:
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url.strip() or not organization_id.strip():
        return {"pass": False, "failures": [{"name": "missing_db_context", "count": 1, "sample_ids": []}]}
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        era_ids = db.execute(
            select(RevenueEraFile.id).where(RevenueEraFile.organization_id == organization_id)
        ).scalars().all()
        return run_revenue_era_invariants(db, organization_id=organization_id, era_file_ids=list(era_ids))


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not _valid_base_url(args.base_url):
        print("error=invalid_base_url", file=sys.stderr)
        return 1
    pdf_dir = Path(args.dir).expanduser().resolve()
    if not pdf_dir.exists() or not pdf_dir.is_dir():
        print(f"error=invalid_dir path={pdf_dir}", file=sys.stderr)
        return 1
    pdfs = sorted(path for path in pdf_dir.iterdir() if path.is_file() and path.suffix.lower() == ".pdf")
    if not pdfs:
        print("error=no_pdf_fixtures", file=sys.stderr)
        return 1

    token = args.token.strip()
    organization_id = args.organization_id.strip()
    if not token:
        token, organization_id = _login(args.base_url, email=args.email, password=args.password)
    if not token:
        print("error=login_failed", file=sys.stderr)
        return 1
    if not organization_id:
        print("error=missing_organization_id", file=sys.stderr)
        return 1

    tasks: list[Path] = []
    for _ in range(max(args.iterations, 1)):
        tasks.extend(pdfs)
    if not tasks:
        print("error=no_tasks", file=sys.stderr)
        return 1

    failures_by_code: Counter[str] = Counter()
    failed_request_ids: list[str] = []
    stage_durations: dict[str, list[int]] = defaultdict(list)
    total_durations: list[int] = []
    deterministic_by_file: dict[str, list[str]] = defaultdict(list)
    worker_rss_samples: list[float] = []
    success_count = 0
    failure_count = 0
    worker_timeout_or_crash = False
    worker_timeout = max(args.job_timeout_seconds, 1.0)

    if args.mode == "processes":
        # Use spawn for clean interpreter/process isolation under stress runs.
        mp_context = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=max(args.workers, 1), mp_context=mp_context) as pool:
            futures = [pool.submit(_run_one_worker, (args.base_url, token, str(path))) for path in tasks]
            for future in futures:
                try:
                    outcome = future.result(timeout=worker_timeout)
                except CFTimeoutError:
                    failure_count += 1
                    failures_by_code["worker_timeout"] += 1
                    worker_timeout_or_crash = True
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                except Exception as exc:
                    failure_count += 1
                    failures_by_code[f"load_runner_{type(exc).__name__}"] += 1
                    worker_timeout_or_crash = True
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                total_durations.append(outcome["duration_ms"])
                worker_rss_samples.append(float(outcome.get("rss_mb", 0.0)))
                for stage, duration in outcome["stage_durations"].items():
                    stage_durations[stage].append(duration)
                if outcome["deterministic_hash"]:
                    deterministic_by_file[outcome["source_file"]].append(outcome["deterministic_hash"])
                if outcome["ok"]:
                    success_count += 1
                else:
                    failure_count += 1
                    failures_by_code[outcome["error_code"]] += 1
                    failed_request_ids.append(outcome["request_id"])
    else:
        with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as pool:
            futures = [pool.submit(_run_one, args.base_url, token=token, pdf_path=path) for path in tasks]
            for future in futures:
                try:
                    outcome = future.result(timeout=worker_timeout)
                except CFTimeoutError:
                    failure_count += 1
                    failures_by_code["worker_timeout"] += 1
                    worker_timeout_or_crash = True
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                except Exception as exc:
                    failure_count += 1
                    failures_by_code[f"load_runner_{type(exc).__name__}"] += 1
                    worker_timeout_or_crash = True
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                total_durations.append(outcome["duration_ms"])
                worker_rss_samples.append(float(outcome.get("rss_mb", 0.0)))
                for stage, duration in outcome["stage_durations"].items():
                    stage_durations[stage].append(duration)
                if outcome["deterministic_hash"]:
                    deterministic_by_file[outcome["source_file"]].append(outcome["deterministic_hash"])
                if outcome["ok"]:
                    success_count += 1
                else:
                    failure_count += 1
                    failures_by_code[outcome["error_code"]] += 1
                    failed_request_ids.append(outcome["request_id"])

    deterministic_failures: list[dict[str, object]] = []
    for file_name, signatures in deterministic_by_file.items():
        unique_hashes = sorted(set(signatures))
        if len(unique_hashes) > 1:
            deterministic_failures.append(
                {"name": "nondeterministic_output", "count": len(unique_hashes), "sample_ids": [file_name]}
            )

    invariants = _run_invariants(organization_id=organization_id)
    max_memory = max(worker_rss_samples + [_rss_mb()]) if worker_rss_samples else _rss_mb()

    summary = {
        "mode": args.mode,
        "workers": args.workers,
        "iterations": args.iterations,
        "success_rate": round(success_count / len(tasks), 4),
        "failure_rate": round(failure_count / len(tasks), 4),
        "failure_rate_by_error_code": dict(failures_by_code),
        "failed_request_ids": failed_request_ids,
        "latency_ms": {
            "p50": _percentile(total_durations, 50),
            "p95": _percentile(total_durations, 95),
            "p99": _percentile(total_durations, 99),
            "mean": int(statistics.mean(total_durations)) if total_durations else 0,
        },
        "stage_latency_ms": {
            stage: {"p50": _percentile(values, 50), "p95": _percentile(values, 95), "p99": _percentile(values, 99)}
            for stage, values in stage_durations.items()
        },
        "max_rss_mb": round(max_memory, 2),
        "memory_ceiling_mb": args.memory_ceiling_mb,
        "determinism_failures": deterministic_failures,
        "db_invariants": invariants if invariants.get("pass", False) else invariants,
    }
    print(json.dumps(summary, sort_keys=True))

    if max_memory > args.memory_ceiling_mb:
        return 1
    if worker_timeout_or_crash:
        return 1
    if not invariants.get("pass", False):
        return 1
    if deterministic_failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
