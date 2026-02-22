import os
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal

router = APIRouter()


class HealthResponse(BaseModel):
    ok: bool


class VersionResponse(BaseModel):
    commit_sha: str


def _azure_ready_status() -> tuple[bool, str]:
    required = [
        "AZURE_DOCINTEL_ENDPOINT",
        "AZURE_DOCINTEL_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_DEPLOYMENT",
    ]
    missing = [key for key in required if not (os.getenv(key, "") or "").strip()]
    env_name = (os.getenv("ENV", "") or os.getenv("APP_ENV", "")).strip().lower()
    if missing:
        if env_name in {"test", "dev", "development"}:
            return True, "disabled"
        return False, "missing_config"
    return True, "ok"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True)


@router.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


# This will become /api/v1/version because of the router prefix
@router.get("/version", response_model=VersionResponse)
def version() -> VersionResponse:
    return VersionResponse(
        commit_sha=os.getenv("COMMIT_SHA", "").strip() or "unknown"
    )


@router.get("/health/db")
def health_db():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    finally:
        db.close()


@router.get("/readyz")
def readyz() -> object:
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"ok": False, "database": "error", "azure": "unknown"})
    finally:
        db.close()
    azure_ready, azure_status = _azure_ready_status()
    if not azure_ready:
        return JSONResponse(status_code=503, content={"ok": False, "database": "ok", "azure": azure_status})
    return {"ok": True, "database": "ok", "azure": azure_status}
