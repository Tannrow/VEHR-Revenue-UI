import logging
import os
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response
from sqlalchemy import text

from app.api.v1.router import api_router
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
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
    default_origins = [
        "https://app.360-encompass.com",
        "http://localhost:3000",
    ]
    if not raw:
        return default_origins
    if raw == "*":
        # Credentials-based auth (cookies) must not use wildcard origins.
        logger.warning("CORS_ALLOWED_ORIGINS='*' is unsafe with allow_credentials; using defaults instead.")
        return default_origins

    configured = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if not configured:
        logger.warning("CORS_ALLOWED_ORIGINS was set but empty; using defaults instead.")
        return default_origins

    # Do not silently allow localhost/default domains once explicit origins are configured.
    if "*" in configured:
        logger.warning("CORS_ALLOWED_ORIGINS included '*', which is unsafe with allow_credentials; ignoring '*'.")
        configured = [origin for origin in configured if origin != "*"]
        if not configured:
            return default_origins

    return sorted(set(configured))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import app.db.models  # register models

    _log_auth_dependency_versions()
    try:
        validate_ringcentral_startup_configuration()
    except RingCentralRealtimeError as exc:
        logger.exception("RingCentral startup validation failed")
        raise RuntimeError(exc.detail) from exc

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
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "*"],
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
