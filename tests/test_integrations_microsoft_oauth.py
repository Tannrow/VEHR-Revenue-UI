from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN
from app.core.security import JWT_ALGORITHM, create_access_token, hash_password
from app.db.base import Base
from app.db.models.audit_event import AuditEvent
from app.db.models.integration_account import IntegrationAccount
from app.db.models.user_microsoft_connection import UserMicrosoftConnection
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.user import User
from app.db.session import get_db
from app.main import app
from app.services.integration_tokens import decrypt_token


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _build_session(tmp_path):
    database_file = tmp_path / "integrations_microsoft_oauth.sqlite"
    engine = create_engine(
        f"sqlite:///{database_file}",
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    from app.db import models as _models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return engine, testing_session_local


def _seed_admin_token(session_factory) -> tuple[str, str, str]:
    with session_factory() as db:
        org = Organization(name="Microsoft OAuth Org")
        db.add(org)
        db.flush()

        user = User(
            email="microsoft-admin@example.com",
            full_name="Microsoft Admin",
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
        return token, org.id, user.id


def test_microsoft_connect_and_callback_upserts_account(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MS_CLIENT_ID", "client-id-123")
    monkeypatch.setenv("MS_CLIENT_SECRET", "client-secret-123")
    monkeypatch.setenv(
        "MS_REDIRECT_URI",
        "https://api.360-encompass.com/api/v1/integrations/microsoft/callback",
    )
    monkeypatch.setenv(
        "MS_GRAPH_SCOPES",
        "openid profile email offline_access User.Read Sites.Read.All Files.ReadWrite.All",
    )
    monkeypatch.setenv(
        "MS_POST_CONNECT_REDIRECT",
        "https://360-encompass.com/admin/integrations/microsoft",
    )
    monkeypatch.setenv("INTEGRATION_TOKEN_KEY", "integration-token-key-for-tests")

    engine, session_factory = _build_session(tmp_path)
    try:
        token, org_id, expected_user_id = _seed_admin_token(session_factory)
        user_id = expected_user_id

        id_token = jwt.encode(
            {
                "tid": "tenant-123",
                "oid": "oid-456",
                "preferred_username": "ms.user@example.com",
            },
            "unit-test-secret",
            algorithm=JWT_ALGORITHM,
        )

        class FakeTokenResponse:
            status_code = 200

            def json(self):
                return {
                    "access_token": "access-token-value",
                    "refresh_token": "refresh-token-value",
                    "id_token": id_token,
                    "scope": "offline_access User.Read",
                    "token_type": "Bearer",
                }

        def fake_post(url, data=None, headers=None, timeout=None):  # noqa: ANN001
            assert url == "https://login.microsoftonline.com/common/oauth2/v2.0/token"
            assert data["grant_type"] == "authorization_code"
            assert data["client_id"] == "client-id-123"
            assert data["client_secret"] == "client-secret-123"
            assert data["redirect_uri"] == "https://api.360-encompass.com/api/v1/integrations/microsoft/callback"
            assert data["scope"] == "openid profile email offline_access User.Read Sites.Read.All Files.ReadWrite.All"
            assert data["code"] == "valid-code"
            assert headers["Content-Type"] == "application/x-www-form-urlencoded"
            assert timeout == 20.0
            return FakeTokenResponse()

        monkeypatch.setattr(
            "app.api.v1.endpoints.integrations_microsoft.httpx.post",
            fake_post,
        )

        with TestClient(app) as client:
            connect_response = client.get(
                "/api/v1/integrations/microsoft/connect",
                headers=_auth_header(token),
                follow_redirects=False,
            )
            assert connect_response.status_code == 200
            authorize_url = connect_response.json()["authorization_url"]
            assert authorize_url.startswith(
                "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?"
            )
            parsed = urlparse(authorize_url)
            query = parse_qs(parsed.query)
            assert query["client_id"] == ["client-id-123"]
            assert query["response_type"] == ["code"]
            assert query["response_mode"] == ["query"]
            assert query["redirect_uri"] == [
                "https://api.360-encompass.com/api/v1/integrations/microsoft/callback"
            ]
            assert query["scope"] == [
                "openid profile email offline_access User.Read Sites.Read.All Files.ReadWrite.All"
            ]
            state = query["state"][0]

            callback_response = client.get(
                "/api/v1/integrations/microsoft/callback",
                params={"code": "valid-code", "state": state},
                follow_redirects=False,
            )
            assert callback_response.status_code == 303
            callback_target = callback_response.headers["location"]
            assert callback_target.startswith(
                "https://360-encompass.com/admin/integrations/microsoft"
            )
            callback_query = parse_qs(urlparse(callback_target).query)
            assert callback_query["status"] == ["connected"]

        with session_factory() as db:
            row = db.execute(select(IntegrationAccount)).scalar_one()
            assert row.provider == "microsoft"
            assert row.organization_id == org_id
            assert row.user_id == user_id
            assert row.external_tenant_id == "tenant-123"
            assert row.external_user_id == "oid-456"
            assert row.email == "ms.user@example.com"
            assert row.scopes == "offline_access User.Read"
            assert row.refresh_token_enc
            assert row.refresh_token_enc != "refresh-token-value"
            assert row.revoked_at is None

            connection = db.execute(select(UserMicrosoftConnection)).scalar_one()
            assert connection.organization_id == org_id
            assert connection.user_id == user_id
            assert connection.tenant_id == "tenant-123"
            assert connection.msft_user_id == "oid-456"
            assert "offline_access" in set(connection.scopes)
            assert "User.Read" in set(connection.scopes)
            assert connection.token_cache_encrypted
            assert connection.refresh_token_enc
            assert connection.access_token_enc
            assert connection.expires_at is not None
            assert connection.connected_at is not None
            assert connection.revoked_at is None
            assert isinstance(connection.metadata_json, dict)
            decrypted_cache = decrypt_token(connection.token_cache_encrypted)
            assert isinstance(decrypted_cache, str)
            assert decrypted_cache.strip().startswith("{")

            audit_event = db.execute(
                select(AuditEvent).where(AuditEvent.action == "microsoft.connected")
            ).scalar_one_or_none()
            assert audit_event is not None
            assert audit_event.organization_id == org_id
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_microsoft_callback_rejects_invalid_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MS_CLIENT_ID", "client-id-123")
    monkeypatch.setenv("MS_CLIENT_SECRET", "client-secret-123")
    monkeypatch.setenv(
        "MS_REDIRECT_URI",
        "https://api.360-encompass.com/api/v1/integrations/microsoft/callback",
    )
    monkeypatch.setenv("MS_POST_CONNECT_REDIRECT", "https://360-encompass.com/admin/integrations/microsoft")

    engine, session_factory = _build_session(tmp_path)
    try:
        _token, _org_id, _user_id = _seed_admin_token(session_factory)

        with TestClient(app) as client:
            callback_response = client.get(
                "/api/v1/integrations/microsoft/callback",
                params={"code": "valid-code", "state": "tampered-state"},
                follow_redirects=False,
            )
            assert callback_response.status_code == 303
            target = callback_response.headers["location"]
            assert target.startswith("https://360-encompass.com/admin/integrations/microsoft")
            parsed = parse_qs(urlparse(target).query)
            assert parsed["status"] == ["error"]
            assert parsed["reason"] == ["invalid_state"]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_microsoft_test_connection_endpoint(tmp_path, monkeypatch) -> None:
    engine, session_factory = _build_session(tmp_path)
    try:
        token, org_id, seeded_user_id = _seed_admin_token(session_factory)

        def fake_profile(*, db, organization_id, user_id):  # noqa: ANN001
            assert organization_id == org_id
            assert user_id == seeded_user_id
            return {
                "displayName": "Graph User",
                "userPrincipalName": "graph.user@example.com",
            }

        monkeypatch.setattr(
            "app.api.v1.endpoints.integrations_microsoft.get_microsoft_graph_profile",
            fake_profile,
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/integrations/microsoft/test",
                headers=_auth_header(token),
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["display_name"] == "Graph User"
            assert payload["user_principal_name"] == "graph.user@example.com"

        with session_factory() as db:
            audit_event = db.execute(
                select(AuditEvent).where(AuditEvent.action == "microsoft.test_connection")
            ).scalar_one_or_none()
            assert audit_event is not None
            assert audit_event.organization_id == org_id
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_microsoft_disconnect_revokes_connection(tmp_path, monkeypatch) -> None:
    engine, session_factory = _build_session(tmp_path)
    try:
        token, org_id, user_id = _seed_admin_token(session_factory)

        with session_factory() as db:
            db.add(
                IntegrationAccount(
                    organization_id=org_id,
                    user_id=user_id,
                    provider="microsoft",
                    external_tenant_id="tenant-1",
                    external_user_id="user-1",
                    email="user@example.com",
                    scopes="User.Read",
                    refresh_token_enc="refresh-enc",
                    revoked_at=None,
                )
            )
            db.add(
                UserMicrosoftConnection(
                    organization_id=org_id,
                    user_id=user_id,
                    tenant_id="tenant-1",
                    msft_user_id="user-1",
                    scopes=["User.Read"],
                    token_cache_encrypted="cache-enc",
                    refresh_token_enc="refresh-enc",
                    access_token_enc="access-enc",
                    metadata_json={},
                    todo_list_id="todo-1",
                )
            )
            db.commit()

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/integrations/microsoft/disconnect",
                headers=_auth_header(token),
            )
            assert response.status_code == 200
            assert response.json()["status"] == "disconnected"

        with session_factory() as db:
            account = db.execute(select(IntegrationAccount)).scalar_one()
            assert account.revoked_at is not None
            connection = db.execute(select(UserMicrosoftConnection)).scalar_one()
            assert connection.revoked_at is not None
            assert connection.access_token_enc is None
            assert connection.refresh_token_enc is None
            assert connection.todo_list_id is None

            audit_event = db.execute(
                select(AuditEvent).where(AuditEvent.action == "microsoft.disconnected")
            ).scalar_one_or_none()
            assert audit_event is not None
            assert audit_event.organization_id == org_id
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_microsoft_refresh_endpoint(tmp_path, monkeypatch) -> None:
    engine, session_factory = _build_session(tmp_path)
    try:
        token, org_id, expected_user_id = _seed_admin_token(session_factory)
        user_id = expected_user_id

        def fake_refresh(*, db, organization_id, user_id):  # noqa: ANN001
            assert organization_id == org_id
            assert user_id == expected_user_id
            return None

        monkeypatch.setattr(
            "app.api.v1.endpoints.integrations_microsoft.refresh_microsoft_connection_tokens",
            fake_refresh,
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/integrations/microsoft/refresh",
                headers=_auth_header(token),
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == "refreshed"

        with session_factory() as db:
            audit_event = db.execute(
                select(AuditEvent).where(AuditEvent.action == "microsoft.refresh_connection")
            ).scalar_one_or_none()
            assert audit_event is not None
            assert audit_event.organization_id == org_id
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
