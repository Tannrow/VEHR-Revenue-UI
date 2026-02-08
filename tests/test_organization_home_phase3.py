from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN, ROLE_CLINICIAN, ROLE_COMPLIANCE, ROLE_STAFF
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


def _create_org(db, *, name: str) -> Organization:
    org = Organization(name=name)
    db.add(org)
    db.flush()
    return org


def _create_user_membership(db, *, org_id: str, email: str, role: str) -> User:
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
            organization_id=org_id,
            user_id=user.id,
            role=role,
        )
    )
    db.flush()
    return user


def test_organization_home_is_tenant_scoped(tmp_path) -> None:
    database_file = tmp_path / "phase3_organization_tenant_scope.sqlite"
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
            org_a = _create_org(db, name="Org A")
            org_b = _create_org(db, name="Org B")
            admin_a = _create_user_membership(
                db,
                org_id=org_a.id,
                email="phase3-admin-a@example.com",
                role=ROLE_ADMIN,
            )
            admin_b = _create_user_membership(
                db,
                org_id=org_b.id,
                email="phase3-admin-b@example.com",
                role=ROLE_ADMIN,
            )
            db.commit()

            token_a = create_access_token({"sub": admin_a.id, "org_id": org_a.id})
            token_b = create_access_token({"sub": admin_b.id, "org_id": org_b.id})

        with TestClient(app) as client:
            home_a = client.get("/api/v1/organization/home", headers=_auth_header(token_a))
            assert home_a.status_code == 200
            tiles_a = home_a.json()["tiles"]
            assert len(tiles_a) > 0

            home_b = client.get("/api/v1/organization/home", headers=_auth_header(token_b))
            assert home_b.status_code == 200
            tiles_b = home_b.json()["tiles"]
            assert len(tiles_b) > 0
            assert not set(tile["id"] for tile in tiles_a) & set(tile["id"] for tile in tiles_b)

            tile_a_id = client.get(
                "/api/v1/organization/tiles?include_inactive=true&for_settings=true",
                headers=_auth_header(token_a),
            ).json()[0]["id"]

            create_announcement = client.post(
                "/api/v1/organization/announcements",
                json={
                    "title": "Org A update",
                    "body": "A-only announcement",
                    "start_date": "2026-02-01",
                    "end_date": None,
                    "is_active": True,
                },
                headers=_auth_header(token_a),
            )
            assert create_announcement.status_code == 201

            list_b = client.get(
                "/api/v1/organization/announcements?include_inactive=true&for_settings=true",
                headers=_auth_header(token_b),
            )
            assert list_b.status_code == 200
            assert all(row["title"] != "Org A update" for row in list_b.json())

            cross_tenant_patch = client.patch(
                f"/api/v1/organization/tiles/{tile_a_id}",
                json={"title": "cross-tenant"},
                headers=_auth_header(token_b),
            )
            assert cross_tenant_patch.status_code == 404
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_organization_settings_endpoints_enforce_rbac(tmp_path) -> None:
    database_file = tmp_path / "phase3_organization_rbac.sqlite"
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
            org = _create_org(db, name="Org RBAC")
            admin = _create_user_membership(
                db,
                org_id=org.id,
                email="phase3-admin@example.com",
                role=ROLE_ADMIN,
            )
            staff = _create_user_membership(
                db,
                org_id=org.id,
                email="phase3-staff@example.com",
                role=ROLE_STAFF,
            )
            db.commit()

            admin_token = create_access_token({"sub": admin.id, "org_id": org.id})
            staff_token = create_access_token({"sub": staff.id, "org_id": org.id})

        with TestClient(app) as client:
            # Staff can access read-only org home.
            staff_home = client.get("/api/v1/organization/home", headers=_auth_header(staff_token))
            assert staff_home.status_code == 200

            staff_settings_tiles = client.get(
                "/api/v1/organization/tiles?include_inactive=true&for_settings=true",
                headers=_auth_header(staff_token),
            )
            assert staff_settings_tiles.status_code == 403

            staff_create_tile = client.post(
                "/api/v1/organization/tiles",
                json={
                    "title": "Restricted Tile",
                    "icon": "layers",
                    "category": "Staff/Ops",
                    "link_type": "internal_route",
                    "href": "/organization/home",
                    "sort_order": 900,
                    "required_permissions": [],
                    "is_active": True,
                },
                headers=_auth_header(staff_token),
            )
            assert staff_create_tile.status_code == 403

            admin_create_tile = client.post(
                "/api/v1/organization/tiles",
                json={
                    "title": "Admin Tile",
                    "icon": "layers",
                    "category": "Staff/Ops",
                    "link_type": "internal_route",
                    "href": "/organization/settings",
                    "sort_order": 910,
                    "required_permissions": ["org:manage"],
                    "is_active": True,
                },
                headers=_auth_header(admin_token),
            )
            assert admin_create_tile.status_code == 201

            staff_visible_tiles = client.get(
                "/api/v1/organization/tiles",
                headers=_auth_header(staff_token),
            )
            assert staff_visible_tiles.status_code == 200
            assert all(tile["title"] != "Admin Tile" for tile in staff_visible_tiles.json())

            staff_create_announcement = client.post(
                "/api/v1/organization/announcements",
                json={
                    "title": "Forbidden",
                    "body": "Staff should not create this",
                    "start_date": "2026-02-01",
                    "end_date": None,
                    "is_active": True,
                },
                headers=_auth_header(staff_token),
            )
            assert staff_create_announcement.status_code == 403
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_my_work_widget_is_role_aware(tmp_path) -> None:
    database_file = tmp_path / "phase3_my_work_roles.sqlite"
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
            org = _create_org(db, name="Org Work Summary")
            clinician = _create_user_membership(
                db,
                org_id=org.id,
                email="phase3-clinician@example.com",
                role=ROLE_CLINICIAN,
            )
            compliance = _create_user_membership(
                db,
                org_id=org.id,
                email="phase3-compliance@example.com",
                role=ROLE_COMPLIANCE,
            )
            db.commit()

            clinician_token = create_access_token({"sub": clinician.id, "org_id": org.id})
            compliance_token = create_access_token({"sub": compliance.id, "org_id": org.id})

        with TestClient(app) as client:
            clinician_summary = client.get("/api/v1/me/work-summary", headers=_auth_header(clinician_token))
            assert clinician_summary.status_code == 200
            assert clinician_summary.json()["show_widget"] is True
            assert len(clinician_summary.json()["items"]) >= 1

            compliance_summary = client.get("/api/v1/me/work-summary", headers=_auth_header(compliance_token))
            assert compliance_summary.status_code == 200
            assert compliance_summary.json()["show_widget"] is False
            assert compliance_summary.json()["items"] == []
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
