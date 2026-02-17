import logging
import os
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.env import truthy_env
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.services.ringcentral_realtime import (
    RingCentralRealtimeError,
    validate_ringcentral_startup_configuration,
)
from app.services.storage import should_validate_s3_on_startup, validate_s3_connection
from app.services.tanner_ai.service import (
    TannerAIConfigurationError,
    validate_tanner_ai_startup_configuration,
)

logger = logging.getLogger(__name__)

_DEFAULT_CORS_ORIGINS = [
    "https://360-encompass.com",
    "https://www.360-encompass.com",
    "https://app.360-encompass.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

_CORS_ENV_KEYS: tuple[str, ...] = (
    "CORS_ALLOWED_ORIGINS",
    "CORS_ORIGINS",
)


def _safe_package_version(package_name: str) -> str:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return "not-installed"
    except Exception:
        return "unknown"


def _log_auth_dependency_versions() -> None:
    # Startup visibility only; this should never block API boot.
    try:
        logger.info(
            "Auth dependency versions: passlib=%s bcrypt=%s",
            _safe_package_version("passlib"),
            _safe_package_version("bcrypt"),
        )
    except Exception:
        logger.exception("Unable to log auth dependency versions")


def get_cors_origins() -> list[str]:
    raw = ""
    source_key: str | None = None
    for key in _CORS_ENV_KEYS:
        value = os.getenv(key, "").strip()
        if value:
            raw = value
            source_key = key
            break

    default_origins = sorted(set(_DEFAULT_CORS_ORIGINS))
    if not raw:
        return default_origins
    if raw == "*":
        # Credentials-based auth (cookies) must not use wildcard origins.
        logger.warning("%s='*' is unsafe with allow_credentials; using defaults instead.", source_key or "CORS_ORIGINS")
        return default_origins

    configured: list[str] = []
    for token in raw.split(","):
        origin = token.strip().rstrip("/")
        if not origin:
            continue
        if origin == "*":
            continue
        configured.append(origin)

    configured = sorted(set(configured))
    if not configured:
        logger.warning("%s was set but empty; using defaults instead.", source_key or "CORS_ORIGINS")
        return default_origins

    # Keep a safe baseline even when env is explicitly configured to avoid accidental lockout.
    return sorted(set(default_origins + configured))


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


def _skip_startup_checks() -> bool:
    if truthy_env("SKIP_STARTUP_CHECKS"):
        return True
    env = os.getenv("ENV", "").strip().lower()
    return env in {"dev", "local"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import app.db.models  # register models


    _log_auth_dependency_versions()
    cors_origins = get_cors_origins()
    logger.info("CORS origins configured: %s", len(cors_origins))
    logger.info("CORS origins: %s", ",".join(cors_origins))
    logger.info("CORS origin hosts: %s", ",".join(_cors_origin_hosts(cors_origins)))
    if _skip_startup_checks():
        logger.info("Skipping startup validation (dev mode enabled)")
    else:
        try:
            validate_ringcentral_startup_configuration()
        except RingCentralRealtimeError as exc:
            logger.exception("RingCentral startup validation failed")
            raise RuntimeError(exc.detail) from exc

    if not _skip_startup_checks() and truthy_env("TANNER_AI_ENABLED"):
        try:
            validate_tanner_ai_startup_configuration()
        except TannerAIConfigurationError as exc:
            logger.exception("Tanner AI startup validation failed")
            raise RuntimeError(str(exc)) from exc

    if should_validate_s3_on_startup():
        # Optional production guard: fail boot if bucket/credentials are invalid.
        validate_s3_connection()

    auto_create = os.getenv("AUTO_CREATE_TABLES", "").strip().lower() in {"1", "true", "yes"}
    if auto_create:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="VEHR API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    has_allow_origin = "access-control-allow-origin" in response.headers
    if response.status_code < 400 and has_allow_origin:
        logger.info(
            "cors_preflight_success path=%s origin=%s status=%s",
            path,
            origin,
            response.status_code,
        )
    else:
        logger.warning(
            "cors_preflight_failure path=%s origin=%s status=%s allow_origin_header=%s",
            path,
            origin,
            response.status_code,
            response.headers.get("access-control-allow-origin"),
        )
    return response

app.include_router(api_router)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/health/db")
def health_db():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    finally:
        db.close()
    return {"status": "ok", "db": "ok"}

@app.get("/")
def root():
    return {"status": "VEHR backend running"}
