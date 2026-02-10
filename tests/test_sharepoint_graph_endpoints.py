from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.user import User
from app.db.session import get_db
from app.main import app
from app.services.microsoft_graph import (
    MicrosoftGraphServiceError,
    SharePointDownloadPayload,
    SharePointDrive,
    SharePointItem,
    SharePointItemPreview,
    SharePointSite,
    SharePointWorkspace,
)


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _build_session(tmp_path):
    database_file = tmp_path / "sharepoint_workspace.sqlite"
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
        org = Organization(name="SharePoint Graph Org")
        db.add(org)
        db.flush()

        user = User(
            email="sharepoint-graph-admin@example.com",
            full_name="SharePoint Graph Admin",
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


def test_sharepoint_workspace_routes_smoke(tmp_path, monkeypatch) -> None:
    engine, session_factory = _build_session(tmp_path)
    try:
        token, org_id, seeded_user_id = _seed_admin_token(session_factory)

        def fake_workspace(*, db, organization_id, user_id):  # noqa: ANN001
            assert organization_id == org_id
            assert user_id == seeded_user_id
            return SharePointWorkspace(
                site=SharePointSite(
                    id="site-allowed",
                    name="Valley Health Home Page",
                    web_url="https://valleyhealthandcounseling.sharepoint.com/sites/ValleyHealthHomePage",
                ),
                drives=[
                    SharePointDrive(
                        id="drive-1",
                        name="Documents",
                        web_url="https://valleyhealthandcounseling.sharepoint.com/sites/ValleyHealthHomePage/Documents",
                    )
                ],
            )

        def fake_items(*, db, organization_id, user_id, drive_id, parent_id):  # noqa: ANN001
            assert organization_id == org_id
            assert user_id == seeded_user_id
            assert drive_id == "drive-1"
            if parent_id == "root":
                return [
                    SharePointItem(
                        id="folder-1",
                        name="Policies",
                        is_folder=True,
                        size=None,
                        web_url="https://contoso.sharepoint.com/folder",
                        last_modified="2026-02-10T00:00:00Z",
                        mime_type=None,
                    ),
                    SharePointItem(
                        id="file-1",
                        name="Guide.pdf",
                        is_folder=False,
                        size=1234,
                        web_url="https://contoso.sharepoint.com/file",
                        last_modified="2026-02-10T00:00:00Z",
                        mime_type="application/pdf",
                    ),
                ]

            assert parent_id == "folder-1"
            return [
                SharePointItem(
                    id="file-2",
                    name="Nested.png",
                    is_folder=False,
                    size=2048,
                    web_url="https://contoso.sharepoint.com/file2",
                    last_modified="2026-02-10T00:00:00Z",
                    mime_type="image/png",
                )
            ]

        def fake_preview(*, db, organization_id, user_id, item_id, drive_id):  # noqa: ANN001
            assert organization_id == org_id
            assert user_id == seeded_user_id
            assert item_id == "file-1"
            assert drive_id == "drive-1"
            return SharePointItemPreview(
                id="file-1",
                name="Guide.pdf",
                web_url="https://contoso.sharepoint.com/file",
                mime_type="application/pdf",
                preview_kind="pdf",
                is_previewable=True,
                preview_url=None,
                download_url="/api/v1/integrations/microsoft/sharepoint/items/file-1/download?driveId=drive-1",
            )

        def fake_download(*, db, organization_id, user_id, item_id, drive_id):  # noqa: ANN001
            assert organization_id == org_id
            assert user_id == seeded_user_id
            assert item_id == "file-1"
            assert drive_id == "drive-1"
            return SharePointDownloadPayload(
                stream=iter([b"PDFDATA"]),
                filename="Guide.pdf",
                content_type="application/pdf",
                content_length=7,
                web_url="https://contoso.sharepoint.com/file",
            )

        monkeypatch.setattr(
            "app.api.v1.endpoints.integrations_microsoft.get_sharepoint_workspace",
            fake_workspace,
        )
        monkeypatch.setattr(
            "app.api.v1.endpoints.integrations_microsoft.list_sharepoint_drive_items",
            fake_items,
        )
        monkeypatch.setattr(
            "app.api.v1.endpoints.integrations_microsoft.get_sharepoint_item_preview",
            fake_preview,
        )
        monkeypatch.setattr(
            "app.api.v1.endpoints.integrations_microsoft.get_sharepoint_item_download_by_item",
            fake_download,
        )

        with TestClient(app) as client:
            workspace_response = client.get(
                "/api/v1/integrations/microsoft/sharepoint/workspace",
                headers=_auth_header(token),
            )
            assert workspace_response.status_code == 200
            workspace_payload = workspace_response.json()
            assert workspace_payload["site"]["id"] == "site-allowed"
            assert workspace_payload["drives"][0]["id"] == "drive-1"

            root_items_response = client.get(
                "/api/v1/integrations/microsoft/sharepoint/drives/drive-1/items",
                params={"parentId": "root"},
                headers=_auth_header(token),
            )
            assert root_items_response.status_code == 200
            assert len(root_items_response.json()) == 2

            nested_items_response = client.get(
                "/api/v1/integrations/microsoft/sharepoint/drives/drive-1/items",
                params={"parentId": "folder-1"},
                headers=_auth_header(token),
            )
            assert nested_items_response.status_code == 200
            assert nested_items_response.json()[0]["id"] == "file-2"

            preview_response = client.get(
                "/api/v1/integrations/microsoft/sharepoint/items/file-1/preview",
                params={"driveId": "drive-1"},
                headers=_auth_header(token),
            )
            assert preview_response.status_code == 200
            preview_payload = preview_response.json()
            assert preview_payload["preview_kind"] == "pdf"
            assert preview_payload["is_previewable"] is True
            assert "driveId=drive-1" in preview_payload["download_url"]

            download_response = client.get(
                "/api/v1/integrations/microsoft/sharepoint/items/file-1/download",
                params={"driveId": "drive-1"},
                headers=_auth_header(token),
            )
            assert download_response.status_code == 200
            assert download_response.content == b"PDFDATA"
            assert "application/pdf" in download_response.headers["content-type"]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_sharepoint_workspace_routes_require_auth(tmp_path) -> None:
    engine, _session_factory = _build_session(tmp_path)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/integrations/microsoft/sharepoint/workspace")
            assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_sharepoint_allowlist_enforcement_returns_403(tmp_path, monkeypatch) -> None:
    engine, session_factory = _build_session(tmp_path)
    try:
        token, _org_id, _seeded_user_id = _seed_admin_token(session_factory)

        def deny_workspace(*, db, organization_id, user_id):  # noqa: ANN001
            raise MicrosoftGraphServiceError(
                "Access denied: requested site is outside the allowed SharePoint workspace",
                403,
            )

        def deny_drive(*, db, organization_id, user_id, drive_id, parent_id):  # noqa: ANN001
            raise MicrosoftGraphServiceError(
                "Access denied: requested drive is outside the allowed SharePoint workspace",
                403,
            )

        def deny_item_preview(*, db, organization_id, user_id, item_id, drive_id):  # noqa: ANN001
            raise MicrosoftGraphServiceError(
                "Access denied: requested item is outside the allowed SharePoint workspace",
                403,
            )

        def deny_item_download(*, db, organization_id, user_id, item_id, drive_id):  # noqa: ANN001
            raise MicrosoftGraphServiceError(
                "Access denied: requested item is outside the allowed SharePoint workspace",
                403,
            )

        monkeypatch.setattr(
            "app.api.v1.endpoints.integrations_microsoft.get_sharepoint_workspace",
            deny_workspace,
        )
        monkeypatch.setattr(
            "app.api.v1.endpoints.integrations_microsoft.list_sharepoint_drive_items",
            deny_drive,
        )
        monkeypatch.setattr(
            "app.api.v1.endpoints.integrations_microsoft.get_sharepoint_item_preview",
            deny_item_preview,
        )
        monkeypatch.setattr(
            "app.api.v1.endpoints.integrations_microsoft.get_sharepoint_item_download_by_item",
            deny_item_download,
        )

        with TestClient(app) as client:
            workspace_response = client.get(
                "/api/v1/integrations/microsoft/sharepoint/workspace",
                headers=_auth_header(token),
            )
            assert workspace_response.status_code == 403
            assert "allowed SharePoint workspace" in workspace_response.json()["detail"]

            drive_response = client.get(
                "/api/v1/integrations/microsoft/sharepoint/drives/blocked-drive/items",
                params={"parentId": "root"},
                headers=_auth_header(token),
            )
            assert drive_response.status_code == 403
            assert "allowed SharePoint workspace" in drive_response.json()["detail"]

            preview_response = client.get(
                "/api/v1/integrations/microsoft/sharepoint/items/blocked-item/preview",
                params={"driveId": "blocked-drive"},
                headers=_auth_header(token),
            )
            assert preview_response.status_code == 403
            assert "allowed SharePoint workspace" in preview_response.json()["detail"]

            download_response = client.get(
                "/api/v1/integrations/microsoft/sharepoint/items/blocked-item/download",
                params={"driveId": "blocked-drive"},
                headers=_auth_header(token),
            )
            assert download_response.status_code == 403
            assert "allowed SharePoint workspace" in download_response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
