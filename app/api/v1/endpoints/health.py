import os

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.db.session import SessionLocal

router = APIRouter()

class HealthResponse(BaseModel):
    ok: bool


class VersionResponse(BaseModel):
    commit_sha: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True)


@router.get("/version", response_model=VersionResponse)
def version() -> VersionResponse:
    return VersionResponse(commit_sha=os.getenv("COMMIT_SHA", "").strip() or "unknown")


@router.get("/health/db")
def health_db():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    finally:
        db.close()
