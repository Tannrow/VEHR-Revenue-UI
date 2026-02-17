from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.db.session import SessionLocal

router = APIRouter()

class HealthResponse(BaseModel):
    ok: bool


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True)

@router.get("/health/db")
def health_db():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    finally:
        db.close()
