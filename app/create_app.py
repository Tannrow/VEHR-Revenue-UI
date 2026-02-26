from __future__ import annotations

import json
import logging
import os
import re
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version as pkg_version
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response

from app.core.env import truthy_env

logger = logging.getLogger(__name__)

# Safe baseline defaults. Anything else is configured via env.
_DEFAULT_CORS_ORIGINS = [
    "https://360-encompass.com",
    "https://www.360-encompass.com",
    "https://app.360-encompass.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

_LOCALHOST_ONLY = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# Your code already checks these keys in order.
_CORS_ENV_KEYS: tuple[str, ...] = (
    "CORS_ALLOWED_ORIGINS",
    "CORS_ORIGINS",
)

# Optional regex env key (new)
_CORS_REGEX_ENV_KEYS: tuple[str, ...] = (
    "CORS_ALLOWED_ORIGIN_REGEX",
    "CORS_ORIGIN_REGEX",
)

# Default regex that covers your new UI hostnames on ACA.
# This prevents “new UI app FQDN” from breaking CORS every time you recreate the app.
_DEFAULT_CORS_ORIGIN_REGEX = r"^https:\/\/[a-z0-9-]+(\-\-[a-z0-9-]+)?\.[a-z0-9-]+\.azurecontainerapps\.io$"


def _safe_package_version(package_name: str) -> str:
    try:
        return pkg_version(package_name)
    except PackageNotFoundError:
        return "not-installed"
    except Exception:
        return "unknown"


def _log_auth_dependency_versions() -> None:
    try:
        logger.info(
            "Auth dependency versions: passlib=%s bcrypt=%s",
            _safe_package_version("passlib"),
            _safe_package_version("bcrypt"),
        )
    except Exception:
        logger.exception("Unable to log auth dependency versions")


def _parse_origin_tokens(raw: str) -> list[str]:
    """
    Accepts:
      - CSV: "https://a,https://b"
      - Whitespace/semicolon separated
      - JSON list: ["https://a","https://b"]
    """
    raw = (raw or "").strip()
    if not raw:
        return []

    # Try JSON array first
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if isinstance(x, str) and str(x).strip()]
    except Exception:
        pass

    # Fallback: split on commas/whitespace/semicolons
    return [t for t in re.split(r"[\s,;]+", raw) if t]


def _normalize_origin(origin: str) -> str:
    origin = (origin or "").strip().strip('"\'').rstrip("/")
    return origin


def _cors_origin_hosts(origins: list[str]) -> list[str]:
    hosts: set[str] = set()
    for origin in origins:
        try:
            parsed = urlparse(origin)
            if parsed.hostname:
                hosts.add(parsed.hostname)
            else:
                hosts.add(origin)
        except Exception:
            hosts.add(origin)
    return sorted(hosts)


def get_cors_settings() -> tuple[list[str], str | None, bool]:
    """
    Returns: (allow_origins, allow_origin_regex, allow_credentials)
    """
    allow_credentials = True
    # Optional override if you ever want to turn off credentials explicitly.
    if os.getenv("CORS_ALLOW_CREDENTIALS", "").strip().lower() in {"0", "false", "no"}:
        allow_credentials = False

    # LOCAL_DEV hard locks to localhost-only, regardless of other env.
    if truthy_env("LOCAL_DEV"):
        raw = ""
        source_key: str | None = None
        for key in _CORS_ENV_KEYS:
            value = os.getenv(key, "").strip()
            if value:
                raw = value
                source_key = key
                break

        base = sorted(set(_LOCALHOST_ONLY))
        if not raw:
            return (base, None, allow_credentials)

        if raw == "*":
            logger.warning(
                "%s='*' is unsafe with LOCAL_DEV; using localhost-only.",
                source_key or "CORS_ORIGINS",
            )
            return (base, None, allow_credentials)

        configured: list[str] = []
        for token in _parse_origin_tokens(raw):
            origin = _normalize_origin(token)
            if not origin or origin == "*":
                continue
            parsed = urlparse(origin)
            if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
                continue
            configured.append(origin)

        return (sorted(set(base + configured)), None, allow_credentials)

    # Non-local: normal behavior
    raw = ""
    source_key: str | None = None
    for key in _CORS_ENV_KEYS:
        value = os.getenv(key, "").strip()
        if value:
            raw = value
            source_key = key
            break

    # Optional regex config
    raw_regex = ""
    regex_key: str | None = None
    for key in _CORS_REGEX_ENV_KEYS:
        value = os.getenv(key, "").strip()
        if value:
            raw_regex = value
            regex_key = key
            break

    default_origins = sorted(set(_DEFAULT_CORS_ORIGINS))
    configured: list[str] = []

    if raw:
        if raw == "*":
            # With credentials true, wildcard is unsafe. We refuse it.
            if allow_credentials:
                logger.warning(
                    "%s='*' is unsafe with allow_credentials=True; using defaults + regex instead.",
                    source_key or "CORS_ORIGINS",
                )
            else:
                # If credentials are false, wildcard is acceptable.
                return (["*"], None, allow_credentials)
        else:
            for token in _parse_origin_tokens(raw):
                origin = _normalize_origin(token)
                if not origin or origin == "*":
                    continue
                configured.append(origin)

    allow_origins = sorted(set(default_origins + configured))

    # Regex handling:
    # - If explicitly configured, trust it.
    # - Otherwise, use default regex to allow ACA UI origins.
    allow_origin_regex: str | None = None
    if raw_regex:
        allow_origin_regex = raw_regex
        logger.info("CORS origin regex configured via %s", regex_key or "CORS_ORIGIN_REGEX")
    else:
        # Default is ON unless explicitly disabled
        if os.getenv("CORS_DISABLE_DEFAULT_REGEX", "").strip().lower() not in {"1", "true", "yes"}:
            allow_origin_regex = _DEFAULT_CORS_ORIGIN_REGEX

    # Final safety: if allow_credentials true, do not allow "*" in allow_origins.
    if allow_credentials and "*" in allow_origins:
        allow_origins = [o for o in allow_origins if o != "*"]

    return (allow_origins, allow_origin_regex, allow_credentials)


def _skip_startup_checks() -> list[str]:
    reasons: list[str] = []
    if truthy_env("SKIP_STARTUP_CHECKS"):
        reasons.append("SKIP_STARTUP_CHECKS=1")
    if truthy_env("NEXUS_AGENT_MODE"):
        reasons.append("NEXUS_AGENT_MODE=1")
    return reasons


def create_app(*, enable_startup_validation: bool = True, include_router: bool = True) -> FastAPI:
    app_version = os.getenv("APP_VERSION", "").strip() or _safe_package_version("vehr")
    if app_version in {"not-installed", "unknown"}:
        app_version = ""

    # Compute CORS settings ONCE and reuse them everywhere.
    cors_origins, cors_origin_regex, cors_allow_credentials = get_cors_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if include_router:
            import app.db.models  # register models

        _log_auth_dependency_versions()

        if truthy_env("LOCAL_DEV"):
            logger.warning("Running in LOCAL_DEV mode")

        logger.info("CORS allow_credentials=%s", cors_allow_credentials)
        logger.info("CORS origins configured: %s", len(cors_origins))
        logger.info("CORS origins: %s", ",".join(cors_origins))
        logger.info("CORS origin hosts: %s", ",".join(_cors_origin_hosts(cors_origins)))
        logger.info("CORS origin regex: %s", cors_origin_regex or "(none)")

        skip_reasons = _skip_startup_checks()
        if enable_startup_validation and skip_reasons:
            logger.info("Skipping startup validation (%s)", ", ".join(skip_reasons))
        else:
            if enable_startup_validation and include_router:
                # RingCentral checks are optional based on your existing env.
                if truthy_env("RINGCENTRAL_REALTIME_ENABLED"):
                    from app.services.ringcentral_realtime import (
                        RingCentralRealtimeError,
                        validate_ringcentral_startup_configuration,
                    )

                    try:
                        validate_ringcentral_startup_configuration()
                    except RingCentralRealtimeError as exc:
                        logger.exception("RingCentral startup validation failed")
                        raise RuntimeError(exc.detail) from exc
                else:
                    logger.info("ringcentral_realtime_disabled")

            if enable_startup_validation and truthy_env("TANNER_AI_ENABLED"):
                if not os.getenv("OPENAI_API_KEY", "").strip():
                    logger.exception("Tanner AI startup validation failed")
                    raise RuntimeError("OPENAI_API_KEY is not configured")

                from app.services.tanner_ai.service import (
                    TannerAIConfigurationError,
                    validate_tanner_ai_startup_configuration,
                )

                try:
                    validate_tanner_ai_startup_configuration()
                except TannerAIConfigurationError as exc:
                    logger.exception("Tanner AI startup validation failed")
                    raise RuntimeError(str(exc)) from exc

        if include_router:
            from app.services.storage import should_validate_s3_on_startup, validate_s3_connection
            from app.db.base import Base
            from app.db.session import engine

            if should_validate_s3_on_startup():
                validate_s3_connection()

            auto_create = os.getenv("AUTO_CREATE_TABLES", "").strip().lower() in {"1", "true", "yes"}
            if auto_create:
                Base.metadata.create_all(bind=engine)

        yield

    app = FastAPI(title="VEHR API", version=app_version or "unknown", lifespan=lifespan)

    # CORS MUST be applied early.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=cors_origin_regex,
        allow_credentials=cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
        max_age=600,
    )

    @app.middleware("http")
    async def require_nexus_admin_token(request: Request, call_next):
        if request.url.path.startswith("/api/dev/"):
            expected = os.getenv("NEXUS_ADMIN_TOKEN", "").strip()
            provided = request.headers.get("X-NEXUS-ADMIN-TOKEN", "").strip()
            if not expected or provided != expected:
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)

    @app.middleware("http")
    async def audit_cors_preflight(request: Request, call_next):
        is_preflight = (
            request.method.upper() == "OPTIONS"
            and "origin" in request.headers
            and "access-control-request-method" in request.headers
        )

        response: Response = await call_next(request)

        if not is_preflight:
            return response

        origin = request.headers.get("origin", "")
        path = request.url.path
        allow_origin = response.headers.get("access-control-allow-origin")
        status_code = response.status_code

        # Starlette CORSMiddleware returns 400 for disallowed origin/method/headers.
        if status_code < 400 and allow_origin:
            logger.info("cors_preflight_success path=%s origin=%s status=%s", path, origin, status_code)
        else:
            logger.warning(
                "cors_preflight_failure path=%s origin=%s status=%s allow_origin=%s cors_origins_count=%s cors_regex=%s",
                path,
                origin,
                status_code,
                allow_origin,
                len(cors_origins),
                cors_origin_regex,
            )
        return response

    if include_router:
        from app.api.v1.router import api_router
        from app.api.legacy_api import router as legacy_api_router
        from app.db.session import SessionLocal
        from sqlalchemy import text

        app.include_router(api_router)
        app.include_router(legacy_api_router)

        @app.get("/health/db")
        def health_db():
            db = SessionLocal()
            try:
                db.execute(text("SELECT 1"))
            finally:
                db.close()
            return {"status": "ok", "db": "ok"}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/version")
    def version_info():
        return {
            "commit_sha": os.getenv("COMMIT_SHA", "").strip() or "unknown",
            "app_version": app_version or "unknown",
        }

    @app.get("/")
    def root():
        return {"status": "VEHR backend running"}

    return app
