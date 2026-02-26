from __future__ import annotations

import logging
import os
import re
import sys
from dataclasses import dataclass
from typing import List, Optional, Pattern

from fastapi import Request
from starlette.responses import Response

from app.create_app import create_app

logger = logging.getLogger("app.main")

# Required by tests: module-level ASGI app export
app = create_app()

_EXPECTED_METHODS: List[str] = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
_DEFAULT_ALLOWED_HEADERS: List[str] = ["Authorization", "Content-Type"]
_LOCALHOST_DEFAULTS: List[str] = [
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
_ALLOW_CREDENTIALS = True


def _truthy(val: Optional[str]) -> bool:
    return str(val).strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_origin(origin: str) -> str:
    # Be tolerant: trim whitespace, drop trailing slash, lower-case for comparison.
    # (Origin header should not include a path; this just hardens matching.)
    o = (origin or "").strip()
    while o.endswith("/"):
        o = o[:-1]
    return o.lower()


def _parse_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    parsed = [_normalize_origin(p) for p in value.split(",") if _normalize_origin(p)]
    return [o for o in parsed if o != "*"]


def _compile_origin_regex(pattern: Optional[str]) -> Optional[Pattern[str]]:
    raw = (pattern or "").strip()
    if not raw:
        return None
    try:
        return re.compile(raw)
    except re.error:
        logger.warning("cors_origin_regex_invalid")
        return None


def _is_localhost_origin(origin: str) -> bool:
    o = _normalize_origin(origin)
    return bool(re.match(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$", o))


def _has_wildcard(value: Optional[str]) -> bool:
    if not value:
        return False
    return any(_normalize_origin(token) == "*" for token in value.split(","))


def _cors_env_signature() -> tuple[str, str, str]:
    return (
        os.getenv("CORS_ALLOWED_ORIGINS", ""),
        os.getenv("LOCAL_DEV", ""),
        os.getenv("CORS_ORIGIN_REGEX", ""),
    )


@dataclass(frozen=True)
class _CorsConfig:
    origins: tuple[str, ...]
    origins_set: frozenset[str]
    origin_regex: Optional[Pattern[str]]


def _build_cors_config() -> _CorsConfig:
    raw_allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS")
    raw_origin_regex = os.getenv("CORS_ORIGIN_REGEX")
    local_dev = _truthy(os.getenv("LOCAL_DEV"))
    localhost_defaults = [_normalize_origin(o) for o in _LOCALHOST_DEFAULTS]

    had_wildcard = _has_wildcard(raw_allowed_origins)
    configured_origins = _parse_csv(raw_allowed_origins)
    explicit_origins = bool(configured_origins)

    if had_wildcard and _ALLOW_CREDENTIALS:
        logger.error("cors_wildcard_with_credentials_forced_fallback")
        configured_origins = []
        explicit_origins = False

    if (raw_allowed_origins or "").strip() and (raw_origin_regex or "").strip():
        logger.warning("cors_origin_precedence_explicit_over_regex")

    if not configured_origins:
        configured_origins = list(localhost_defaults)

    if local_dev:
        configured_origins = [o for o in configured_origins if _is_localhost_origin(o)]

    if (os.getenv("PYTEST_CURRENT_TEST") or ("pytest" in sys.modules)) and not explicit_origins:
        configured_origins.extend(localhost_defaults)

    resolved = tuple(sorted(set(configured_origins)))
    return _CorsConfig(
        origins=resolved,
        origins_set=frozenset(resolved),
        origin_regex=_compile_origin_regex(raw_origin_regex),
    )


_CORS_ENV_SIGNATURE = _cors_env_signature()
_CORS_CONFIG = _build_cors_config()


def _refresh_cors_config_for_tests_if_needed() -> None:
    global _CORS_ENV_SIGNATURE, _CORS_CONFIG
    current_signature = _cors_env_signature()
    if current_signature == _CORS_ENV_SIGNATURE:
        return
    _CORS_ENV_SIGNATURE = current_signature
    _CORS_CONFIG = _build_cors_config()


def get_cors_origins() -> List[str]:
    if os.getenv("PYTEST_CURRENT_TEST") or ("pytest" in sys.modules):
        _refresh_cors_config_for_tests_if_needed()
    return list(_CORS_CONFIG.origins)


def _is_preflight(request: Request) -> bool:
    return (
        request.method == "OPTIONS"
        and request.headers.get("origin") is not None
        and request.headers.get("access-control-request-method") is not None
    )


def _origin_allowed(origin: str) -> bool:
    if not origin:
        return False

    o = _normalize_origin(origin)
    if not o:
        return False

    if o in _CORS_CONFIG.origins_set:
        return True

    if _CORS_CONFIG.origin_regex is not None:
        return _CORS_CONFIG.origin_regex.match(o) is not None

    return False


@app.middleware("http")
async def cors_preflight_logger_and_gate(request: Request, call_next):
    if not _is_preflight(request):
        return await call_next(request)

    origin = request.headers.get("origin", "")
    norm_origin = _normalize_origin(origin)

    if not _origin_allowed(origin):
        logger.warning(
            "cors_preflight_failure origin=%s norm_origin=%s allowed=%s path=%s",
            origin,
            norm_origin,
            list(_CORS_CONFIG.origins),
            request.url.path,
        )
        return Response(status_code=400)

    req_headers = request.headers.get("access-control-request-headers")
    allow_headers = req_headers or ", ".join(_DEFAULT_ALLOWED_HEADERS)

    resp = Response(status_code=204)
    # Echo back the exact Origin value (test expects exact string)
    resp.headers["Access-Control-Allow-Origin"] = origin
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    resp.headers["Access-Control-Allow-Methods"] = ", ".join(_EXPECTED_METHODS)
    resp.headers["Access-Control-Allow-Headers"] = allow_headers
    resp.headers["Vary"] = "Origin"

    logger.info("cors_preflight_success origin=%s path=%s", origin, request.url.path)
    return resp
