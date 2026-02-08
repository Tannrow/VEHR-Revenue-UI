from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN, ROLE_STAFF
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


def _create_user_membership(db, *, organization_id: str, email: str, role: str) -> User:
    user = User(
        email=email,
        full_name=email.split("@", 1)[0],
        hashed_password=DUMMY_HASH,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        OrganizationMembership(
            organization_id=organization_id,
            user_id=user.id,
            role=role,
        )
    )
    db.flush()
    return user


def test_workspace_nodes_support_nested_folders_and_files(tmp_path) -> None:
    database_file = tmp_path / "organization_workspace_nodes.sqlite"
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
        with TestingSessionLocal() as db:
            org = Organization(name="Workspace Org")
            db.add(org)
            db.flush()
            admin = _create_user_membership(
                db,
                organization_id=org.id,
                email="workspace-admin@example.com",
                role=ROLE_ADMIN,
            )
            db.commit()
            token = create_access_token({"sub": admin.id, "org_id": org.id})
            organization_id = org.id

        with TestClient(app) as client:
            with patch(
                "app.api.v1.endpoints.organization_home.upload_fileobj",
                return_value=None,
            ):
                home = client.get("/api/v1/organization/home", headers=_auth_header(token))
                assert home.status_code == 200
                tile_id = home.json()["tiles"][0]["id"]

                folder = client.post(
                    f"/api/v1/organization/tiles/{tile_id}/nodes",
                    json={"node_type": "folder", "name": "Status Reports"},
                    headers=_auth_header(token),
                )
                assert folder.status_code == 201
                folder_id = folder.json()["id"]

                file_node = client.post(
                    f"/api/v1/organization/tiles/{tile_id}/nodes",
                    json={
                        "node_type": "file",
                        "name": "Team Meeting 2026-02-08.txt",
                        "content": "Agenda draft",
                    },
                    headers=_auth_header(token),
                )
                assert file_node.status_code == 201
                file_id = file_node.json()["id"]

                subfolder = client.post(
                    f"/api/v1/organization/tiles/{tile_id}/nodes",
                    json={
                        "node_type": "folder",
                        "name": "Week 1",
                        "parent_id": folder_id,
                    },
                    headers=_auth_header(token),
                )
                assert subfolder.status_code == 201
                subfolder_id = subfolder.json()["id"]

                root_nodes = client.get(
                    f"/api/v1/organization/tiles/{tile_id}/nodes",
                    headers=_auth_header(token),
                )
                assert root_nodes.status_code == 200
                root_by_id = {row["id"]: row for row in root_nodes.json()}
                assert root_by_id[folder_id]["node_type"] == "folder"
                assert root_by_id[file_id]["node_type"] == "file"

                nested_nodes = client.get(
                    f"/api/v1/organization/tiles/{tile_id}/nodes?parent_id={folder_id}",
                    headers=_auth_header(token),
                )
                assert nested_nodes.status_code == 200
                assert [row["id"] for row in nested_nodes.json()] == [subfolder_id]

                update_file = client.patch(
                    f"/api/v1/organization/nodes/{file_id}",
                    json={"name": "Team Meeting Final.txt", "content": "Final notes"},
                    headers=_auth_header(token),
                )
                assert update_file.status_code == 200
                assert update_file.json()["name"] == "Team Meeting Final.txt"
                assert update_file.json()["content"] == "Final notes"

                uploaded_asset = client.post(
                    f"/api/v1/organization/tiles/{tile_id}/nodes",
                    json={
                        "node_type": "file",
                        "name": "IOP-Checklist.png",
                        "storage_key": "other-org-id/workspace/2026-02/checklist.png",
                        "media_type": "image/png",
                        "size_bytes": 1024,
                    },
                    headers=_auth_header(token),
                )
                assert uploaded_asset.status_code == 400

                uploaded_asset_ok = client.post(
                    f"/api/v1/organization/tiles/{tile_id}/nodes",
                    json={
                        "node_type": "file",
                        "name": "IOP-Checklist.png",
                        "storage_key": f"{organization_id}/workspace/2026-02/checklist.png",
                        "media_type": "image/png",
                        "size_bytes": 1024,
                    },
                    headers=_auth_header(token),
                )
                assert uploaded_asset_ok.status_code == 201
                assert uploaded_asset_ok.json()["storage_key"] == f"{organization_id}/workspace/2026-02/checklist.png"
                assert uploaded_asset_ok.json()["media_type"] == "image/png"
                assert uploaded_asset_ok.json()["size_bytes"] == 1024

                uploaded_pdf = client.post(
                    f"/api/v1/organization/tiles/{tile_id}/nodes/upload",
                    files={"file": ("Status-Report.pdf", b"%PDF-1.4\nfake", "application/pdf")},
                    data={"parent_id": folder_id},
                    headers=_auth_header(token),
                )
                assert uploaded_pdf.status_code == 201
                assert uploaded_pdf.json()["node_type"] == "file"
                assert uploaded_pdf.json()["media_type"] == "application/pdf"
                assert uploaded_pdf.json()["size_bytes"] > 0
                assert uploaded_pdf.json()["parent_id"] == folder_id
                assert uploaded_pdf.json()["storage_key"].startswith(
                    f"{organization_id}/workspace_{tile_id}/"
                )

                uploaded_png = client.post(
                    f"/api/v1/organization/tiles/{tile_id}/nodes/upload",
                    files={"file": ("scan.png", b"png-binary", "image/png")},
                    data={"existing_node_id": file_id},
                    headers=_auth_header(token),
                )
                assert uploaded_png.status_code == 201
                assert uploaded_png.json()["id"] == file_id
                assert uploaded_png.json()["media_type"] == "image/png"
                assert uploaded_png.json()["storage_key"].startswith(
                    f"{organization_id}/workspace_{tile_id}/"
                )
                assert uploaded_png.json()["content"] is None
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_workspace_nodes_enforce_tenant_and_rbac(tmp_path) -> None:
    database_file = tmp_path / "organization_workspace_nodes_scope.sqlite"
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
        with TestingSessionLocal() as db:
            org_a = Organization(name="Workspace Org A")
            org_b = Organization(name="Workspace Org B")
            db.add(org_a)
            db.add(org_b)
            db.flush()

            admin_a = _create_user_membership(
                db,
                organization_id=org_a.id,
                email="workspace-admin-a@example.com",
                role=ROLE_ADMIN,
            )
            staff_a = _create_user_membership(
                db,
                organization_id=org_a.id,
                email="workspace-staff-a@example.com",
                role=ROLE_STAFF,
            )
            admin_b = _create_user_membership(
                db,
                organization_id=org_b.id,
                email="workspace-admin-b@example.com",
                role=ROLE_ADMIN,
            )
            db.commit()

            admin_a_token = create_access_token({"sub": admin_a.id, "org_id": org_a.id})
            staff_a_token = create_access_token({"sub": staff_a.id, "org_id": org_a.id})
            admin_b_token = create_access_token({"sub": admin_b.id, "org_id": org_b.id})

        with TestClient(app) as client:
            org_a_home = client.get("/api/v1/organization/home", headers=_auth_header(admin_a_token))
            assert org_a_home.status_code == 200
            default_tile_id = org_a_home.json()["tiles"][0]["id"]

            restricted_tile = client.post(
                "/api/v1/organization/tiles",
                json={
                    "title": "Leadership Files",
                    "icon": "layers",
                    "category": "Staff/Ops",
                    "link_type": "internal_route",
                    "href": "/organization/home",
                    "sort_order": 999,
                    "required_permissions": ["org:manage"],
                    "is_active": True,
                },
                headers=_auth_header(admin_a_token),
            )
            assert restricted_tile.status_code == 201
            restricted_tile_id = restricted_tile.json()["id"]

            staff_forbidden = client.get(
                f"/api/v1/organization/tiles/{restricted_tile_id}/nodes",
                headers=_auth_header(staff_a_token),
            )
            assert staff_forbidden.status_code == 403

            cross_tenant_missing_tile = client.get(
                f"/api/v1/organization/tiles/{default_tile_id}/nodes",
                headers=_auth_header(admin_b_token),
            )
            assert cross_tenant_missing_tile.status_code == 404

            created = client.post(
                f"/api/v1/organization/tiles/{default_tile_id}/nodes",
                json={"node_type": "file", "name": "status.txt", "content": "draft"},
                headers=_auth_header(admin_a_token),
            )
            assert created.status_code == 201
            created_node_id = created.json()["id"]

            cross_tenant_update = client.patch(
                f"/api/v1/organization/nodes/{created_node_id}",
                json={"name": "cross-tenant.txt"},
                headers=_auth_header(admin_b_token),
            )
            assert cross_tenant_update.status_code == 404

            with patch(
                "app.api.v1.endpoints.organization_home.upload_fileobj",
                return_value=None,
            ):
                cross_tenant_upload = client.post(
                    f"/api/v1/organization/tiles/{default_tile_id}/nodes/upload",
                    files={"file": ("cross.pdf", b"pdf", "application/pdf")},
                    headers=_auth_header(admin_b_token),
                )
                assert cross_tenant_upload.status_code == 404
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
