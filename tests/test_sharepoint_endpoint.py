from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.endpoints.sharepoint import DEFAULT_SHAREPOINT_HOME_URL
from app.core.rbac import ROLE_ADMIN
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.user import User
from app.db.session import get_db
from app.main import app


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _build_session(tmp_path):
    database_file = tmp_path / "sharepoint_endpoint.sqlite"
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
    return engine, TestingSessionLocal


def _seed_admin_token(session_factory) -> tuple[str, str]:
    with session_factory() as db:
        org = Organization(name="SharePoint Org")
        db.add(org)
        db.flush()

        user = User(
            email="sharepoint-admin@example.com",
            full_name="SharePoint Admin",
            hashed_password=hash_password("AdminPass123!"),
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
        token = create_access_token({"sub": user.id, "org_id": org.id})
        return token, org.id


def test_sharepoint_settings_requires_authentication(tmp_path) -> None:
    engine, session_factory = _build_session(tmp_path)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/org/sharepoint-settings")
            assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_sharepoint_settings_returns_defaults_for_authenticated_org(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SHAREPOINT_HOME_URL", raising=False)
    monkeypatch.delenv("SHAREPOINT_QUICK_LINKS_JSON", raising=False)
    engine, session_factory = _build_session(tmp_path)
    try:
        token, org_id = _seed_admin_token(session_factory)
        with TestClient(app) as client:
            response = client.get("/api/v1/org/sharepoint-settings", headers=_auth_header(token))
            assert response.status_code == 200
            payload = response.json()
            assert payload["home_url"] == DEFAULT_SHAREPOINT_HOME_URL
            assert len(payload["quick_links"]) == 5
            assert [item["label"] for item in payload["quick_links"]] == [
                "Policies",
                "Training",
                "Templates",
                "Contracts",
                "Forms",
            ]
            assert all(item["url"] == DEFAULT_SHAREPOINT_HOME_URL for item in payload["quick_links"])

            # Tenant scoping remains tied to membership org.
            home_response = client.get("/api/v1/sharepoint/home", headers=_auth_header(token))
            assert home_response.status_code == 200
            assert home_response.json()["organization_id"] == org_id
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_sharepoint_settings_uses_valid_env_quick_links(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SHAREPOINT_HOME_URL", DEFAULT_SHAREPOINT_HOME_URL)
    monkeypatch.setenv(
        "SHAREPOINT_QUICK_LINKS_JSON",
        json.dumps(
            [
                {
                    "label": "Policies",
                    "url": "https://valleyhealthandcounseling.sharepoint.com/sites/ValleyHealthHomePage/policies",
                    "description": "Policy library",
                },
                {
                    "label": "Training",
                    "url": "https://valleyhealthandcounseling.sharepoint.com/sites/ValleyHealthHomePage/training",
                },
            ]
        ),
    )
    engine, session_factory = _build_session(tmp_path)
    try:
        token, _org_id = _seed_admin_token(session_factory)
        with TestClient(app) as client:
            response = client.get("/api/v1/org/sharepoint-settings", headers=_auth_header(token))
            assert response.status_code == 200
            payload = response.json()
            assert payload["home_url"] == DEFAULT_SHAREPOINT_HOME_URL
            assert payload["quick_links"] == [
                {
                    "label": "Policies",
                    "url": "https://valleyhealthandcounseling.sharepoint.com/sites/ValleyHealthHomePage/policies",
                    "description": "Policy library",
                },
                {
                    "label": "Training",
                    "url": "https://valleyhealthandcounseling.sharepoint.com/sites/ValleyHealthHomePage/training",
                    "description": None,
                },
            ]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_sharepoint_settings_rejects_non_sharepoint_domain(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SHAREPOINT_HOME_URL", "https://example.com/sites/home")
    monkeypatch.delenv("SHAREPOINT_QUICK_LINKS_JSON", raising=False)
    engine, session_factory = _build_session(tmp_path)
    try:
        token, _org_id = _seed_admin_token(session_factory)
        with TestClient(app) as client:
            response = client.get("/api/v1/org/sharepoint-settings", headers=_auth_header(token))
            assert response.status_code == 500
            assert "sharepoint.com" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_sharepoint_settings_rejects_invalid_quick_link_url(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SHAREPOINT_HOME_URL", DEFAULT_SHAREPOINT_HOME_URL)
    monkeypatch.setenv(
        "SHAREPOINT_QUICK_LINKS_JSON",
        json.dumps(
            [
                {
                    "label": "Policies",
                    "url": "https://example.com/policies",
                }
            ]
        ),
    )
    engine, session_factory = _build_session(tmp_path)
    try:
        token, _org_id = _seed_admin_token(session_factory)
        with TestClient(app) as client:
            response = client.get("/api/v1/org/sharepoint-settings", headers=_auth_header(token))
            assert response.status_code == 500
            assert "sharepoint.com" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_sharepoint_settings_rejects_non_https_home_url(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SHAREPOINT_HOME_URL", "http://tenant.sharepoint.com/sites/home")
    monkeypatch.delenv("SHAREPOINT_QUICK_LINKS_JSON", raising=False)
    engine, session_factory = _build_session(tmp_path)
    try:
        token, _org_id = _seed_admin_token(session_factory)
        with TestClient(app) as client:
            response = client.get("/api/v1/org/sharepoint-settings", headers=_auth_header(token))
            assert response.status_code == 500
            assert "https" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
