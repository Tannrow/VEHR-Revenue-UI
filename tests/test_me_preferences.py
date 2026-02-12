from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN, ROLE_RECEPTIONIST
from app.core.security import create_access_token
from app.db.base import Base
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.user import User
from app.db.session import get_db
from app.main import app


DUMMY_HASH = "test-hash-not-used-in-this-suite"


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_user_with_membership(db, *, role: str) -> tuple[Organization, User]:
    org = Organization(name=f"Prefs Org {role}")
    db.add(org)
    db.flush()

    user = User(
        email=f"prefs-{role}@example.com",
        full_name=f"prefs-{role}",
        hashed_password=DUMMY_HASH,
        is_active=True,
    )
    db.add(user)
    db.flush()

    db.add(
        OrganizationMembership(
            organization_id=org.id,
            user_id=user.id,
            role=role,
        )
    )
    db.commit()
    db.refresh(org)
    db.refresh(user)
    return org, user


def test_me_preferences_get_creates_defaults(tmp_path) -> None:
    database_file = tmp_path / "me_preferences_defaults.sqlite"
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
    try:
        with testing_session() as db:
            org, user = _create_user_with_membership(db, role=ROLE_ADMIN)
            token = create_access_token({"sub": user.id, "org_id": org.id})

        with TestClient(app) as client:
            response = client.get("/api/v1/me/preferences", headers=_auth_header(token))
            assert response.status_code == 200
            payload = response.json()
            assert payload["last_active_module"] is None
            assert payload["sidebar_collapsed"] is False
            assert payload["copilot_enabled"] is True
            assert payload["allowed_modules"]
            assert "administration" in payload["allowed_modules"]

    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_me_preferences_patch_accepts_allowed_module(tmp_path) -> None:
    database_file = tmp_path / "me_preferences_patch_allowed.sqlite"
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
    try:
        with testing_session() as db:
            org, user = _create_user_with_membership(db, role=ROLE_ADMIN)
            token = create_access_token({"sub": user.id, "org_id": org.id})

        with TestClient(app) as client:
            response = client.patch(
                "/api/v1/me/preferences",
                headers=_auth_header(token),
                json={
                    "last_active_module": "care_delivery",
                    "sidebar_collapsed": True,
                    "copilot_enabled": False,
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["last_active_module"] == "care_delivery"
            assert payload["sidebar_collapsed"] is True
            assert payload["copilot_enabled"] is False

    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_me_preferences_patch_rejects_disallowed_module(tmp_path) -> None:
    database_file = tmp_path / "me_preferences_patch_denied.sqlite"
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
    try:
        with testing_session() as db:
            org, user = _create_user_with_membership(db, role=ROLE_RECEPTIONIST)
            token = create_access_token({"sub": user.id, "org_id": org.id})

        with TestClient(app) as client:
            response = client.patch(
                "/api/v1/me/preferences",
                headers=_auth_header(token),
                json={"last_active_module": "governance"},
            )
            assert response.status_code == 403

    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
