from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN
from app.core.security import hash_password
from app.db.base import Base
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.user import User
from app.db.session import get_db
from app.main import app


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_login_then_me_smoke(tmp_path) -> None:
    database_file = tmp_path / "auth_login_me_smoke.sqlite"
    engine = create_engine(
        f"sqlite:///{database_file}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    from app.db import models as _models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        org_id: str
        with TestingSessionLocal() as db:
            org = Organization(name="Auth Smoke Org")
            db.add(org)
            db.flush()
            org_id = org.id

            user = User(
                email="smoke-login@example.com",
                full_name="Smoke Login",
                hashed_password=hash_password("SmokePass123!"),
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

        with TestClient(app) as client:
            login_response = client.post(
                "/api/v1/auth/login",
                json={"email": "smoke-login@example.com", "password": "SmokePass123!"},
            )
            assert login_response.status_code == 200
            token = login_response.json()["access_token"]

            me_response = client.get(
                "/api/v1/auth/me",
                headers=_auth_header(token),
            )
            assert me_response.status_code == 200
            payload = me_response.json()
            assert payload["email"] == "smoke-login@example.com"
            assert payload["organization_id"] == org_id
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
