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
    SharePointDownloadPayload,
    SharePointDrive,
    SharePointItem,
    SharePointSite,
)


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _build_session(tmp_path):
    database_file = tmp_path / "sharepoint_graph.sqlite"
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


def test_sharepoint_graph_routes_smoke(tmp_path, monkeypatch) -> None:
    engine, session_factory = _build_session(tmp_path)
    try:
        token, org_id, seeded_user_id = _seed_admin_token(session_factory)

        def fake_sites(*, db, organization_id, user_id, search):  # noqa: ANN001
            assert organization_id == org_id
            assert user_id == seeded_user_id
            assert search == "valley"
            return [
                SharePointSite(
                    id="site-1",
                    name="Valley Health",
                    web_url="https://contoso.sharepoint.com/sites/ValleyHealth",
                )
            ]

        def fake_drives(*, db, organization_id, user_id, site_id):  # noqa: ANN001
            assert organization_id == org_id
            assert user_id == seeded_user_id
            assert site_id == "site-1"
            return [
                SharePointDrive(
                    id="drive-1",
                    name="Documents",
                    web_url="https://contoso.sharepoint.com/sites/ValleyHealth/Documents",
                )
            ]

        def fake_children(*, db, organization_id, user_id, drive_id, item_id=None):  # noqa: ANN001
            assert organization_id == org_id
            assert user_id == seeded_user_id
            assert drive_id == "drive-1"
            if item_id is None:
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
            assert item_id == "folder-1"
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

        def fake_download(*, db, organization_id, user_id, drive_id, item_id):  # noqa: ANN001
            assert organization_id == org_id
            assert user_id == seeded_user_id
            assert drive_id == "drive-1"
            assert item_id == "file-1"
            return SharePointDownloadPayload(
                stream=iter([b"PDFDATA"]),
                filename="Guide.pdf",
                content_type="application/pdf",
                content_length=7,
                web_url="https://contoso.sharepoint.com/file",
            )

        monkeypatch.setattr(
            "app.api.v1.endpoints.sharepoint_graph.search_sharepoint_sites",
            fake_sites,
        )
        monkeypatch.setattr(
            "app.api.v1.endpoints.sharepoint_graph.list_sharepoint_drives",
            fake_drives,
        )
        monkeypatch.setattr(
            "app.api.v1.endpoints.sharepoint_graph.list_sharepoint_children",
            fake_children,
        )
        monkeypatch.setattr(
            "app.api.v1.endpoints.sharepoint_graph.get_sharepoint_item_download",
            fake_download,
        )

        with TestClient(app) as client:
            sites_response = client.get(
                "/api/v1/sharepoint/sites",
                params={"search": "valley"},
                headers=_auth_header(token),
            )
            assert sites_response.status_code == 200
            assert sites_response.json()[0]["id"] == "site-1"

            drives_response = client.get(
                "/api/v1/sharepoint/sites/site-1/drives",
                headers=_auth_header(token),
            )
            assert drives_response.status_code == 200
            assert drives_response.json()[0]["id"] == "drive-1"

            root_children_response = client.get(
                "/api/v1/sharepoint/drives/drive-1/root/children",
                headers=_auth_header(token),
            )
            assert root_children_response.status_code == 200
            assert len(root_children_response.json()) == 2

            nested_children_response = client.get(
                "/api/v1/sharepoint/drives/drive-1/items/folder-1/children",
                headers=_auth_header(token),
            )
            assert nested_children_response.status_code == 200
            assert nested_children_response.json()[0]["id"] == "file-2"

            download_response = client.get(
                "/api/v1/sharepoint/drives/drive-1/items/file-1/download",
                headers=_auth_header(token),
            )
            assert download_response.status_code == 200
            assert download_response.content == b"PDFDATA"
            assert "application/pdf" in download_response.headers["content-type"]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_sharepoint_graph_routes_require_auth(tmp_path) -> None:
    engine, _session_factory = _build_session(tmp_path)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/sharepoint/sites", params={"search": "valley"})
            assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
