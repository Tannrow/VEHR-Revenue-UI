from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.tanner_ai import get_tanner_service_dependency
from app.core.rbac import ROLE_ADMIN
from app.core.security import create_access_token
from app.db.base import Base
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.user import User
from app.db.session import get_db
from app.main import app


DUMMY_HASH = "test-hash-not-used-in-this-suite"


class _FakeTannerAIService:
    def transcribe_audio(self, file_path: str) -> str:  # noqa: ARG002
        return "sample transcript"

    def generate_text(self, prompt: str, temperature: float = 0.2) -> str:  # noqa: ARG002
        return "generated draft"

    def generate_structured_note(self, transcript: str, note_type: str) -> dict[str, str]:  # noqa: ARG002
        if note_type.strip().upper() == "SOAP":
            return {"S": "s", "O": "o", "A": "a", "P": "p"}
        return {"content": "custom note"}

    def assistant_reply(self, message: str, context: str | None = None) -> str:  # noqa: ARG002
        return "assistant reply"


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_user_with_membership(db) -> tuple[Organization, User]:
    org = Organization(name="Tanner AI Org")
    db.add(org)
    db.flush()

    user = User(
        email="tanner-ai@example.com",
        full_name="Tanner AI Tester",
        hashed_password=DUMMY_HASH,
        is_active=True,
    )
    db.add(user)
    db.flush()

    db.add(
        OrganizationMembership(
            organization_id=org.id,
            user_id=user.id,
            role=ROLE_ADMIN,
        )
    )
    db.commit()
    db.refresh(org)
    db.refresh(user)
    return org, user


def test_tanner_ai_health_ready() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/tanner-ai/health")
        assert response.status_code == 200
        assert response.json() == {"service": "Tanner AI", "status": "ready"}


def test_tanner_ai_authenticated_routes(tmp_path) -> None:
    database_file = tmp_path / "tanner_ai_routes.sqlite"
    engine = create_engine(
        f"sqlite:///{database_file}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    from app.db import models as _models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_tanner_service_dependency] = lambda: _FakeTannerAIService()

    try:
        with testing_session() as db:
            org, user = _create_user_with_membership(db)
            token = create_access_token({"sub": user.id, "org_id": org.id})

        with TestClient(app) as client:
            headers = _auth_header(token)

            generate_response = client.post(
                "/api/v1/tanner-ai/generate",
                headers=headers,
                json={"prompt": "Draft a short email"},
            )
            assert generate_response.status_code == 200
            assert generate_response.json() == {"text": "generated draft"}

            note_response = client.post(
                "/api/v1/tanner-ai/note",
                headers=headers,
                json={"transcript": "patient reports improved sleep", "note_type": "SOAP"},
            )
            assert note_response.status_code == 200
            assert note_response.json() == {"S": "s", "O": "o", "A": "a", "P": "p"}

            assistant_response = client.post(
                "/api/v1/tanner-ai/assistant",
                headers=headers,
                json={"message": "Summarize this meeting agenda"},
            )
            assert assistant_response.status_code == 200
            assert assistant_response.json() == {"reply": "assistant reply"}

            transcribe_response = client.post(
                "/api/v1/tanner-ai/transcribe",
                headers=headers,
                files={"file": ("visit.webm", b"fake-audio-bytes", "audio/webm")},
            )
            assert transcribe_response.status_code == 200
            assert transcribe_response.json() == {"transcript": "sample transcript"}
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_tanner_ai_transcribe_rejects_large_files(tmp_path, monkeypatch) -> None:
    from app.api.v1 import tanner_ai

    database_file = tmp_path / "tanner_ai_upload_limit.sqlite"
    engine = create_engine(
        f"sqlite:///{database_file}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    from app.db import models as _models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(tanner_ai, "MAX_AUDIO_UPLOAD_BYTES", 8)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_tanner_service_dependency] = lambda: _FakeTannerAIService()

    try:
        with testing_session() as db:
            org, user = _create_user_with_membership(db)
            token = create_access_token({"sub": user.id, "org_id": org.id})

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/tanner-ai/transcribe",
                headers=_auth_header(token),
                files={"file": ("visit.webm", b"0123456789", "audio/webm")},
            )
            assert response.status_code == 413
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
