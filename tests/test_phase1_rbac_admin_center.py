from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN, ROLE_CASE_MANAGER, ROLE_RECEPTIONIST
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


def _create_user_membership(
    db,
    *,
    organization_id: str,
    email: str,
    role: str,
) -> User:
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


def test_receptionist_cannot_access_admin_role_endpoints(tmp_path) -> None:
    database_file = tmp_path / "phase1_rbac_receptionist.sqlite"
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
            org = Organization(name="RBAC Org")
            db.add(org)
            db.flush()
            org_id = org.id

            receptionist = _create_user_membership(
                db,
                organization_id=org_id,
                email="reception@example.com",
                role=ROLE_RECEPTIONIST,
            )
            db.commit()
            receptionist_token = create_access_token({"sub": receptionist.id, "org_id": org_id})

        with TestClient(app) as client:
            teams_response = client.get(
                "/api/v1/staff/teams",
                headers=_auth_header(receptionist_token),
            )
            assert teams_response.status_code == 200

            roles_response = client.get(
                "/api/v1/admin/roles",
                headers=_auth_header(receptionist_token),
            )
            assert roles_response.status_code == 403

            invite_response = client.post(
                "/api/v1/admin/invites",
                json={"email": "newhire@example.com", "allowed_roles": [ROLE_CASE_MANAGER]},
                headers=_auth_header(receptionist_token),
            )
            assert invite_response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_admin_can_assign_roles(tmp_path) -> None:
    database_file = tmp_path / "phase1_rbac_assign.sqlite"
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
            org = Organization(name="Role Assign Org")
            db.add(org)
            db.flush()
            org_id = org.id

            admin = _create_user_membership(
                db,
                organization_id=org_id,
                email="admin@example.com",
                role=ROLE_ADMIN,
            )
            target_user = _create_user_membership(
                db,
                organization_id=org_id,
                email="target@example.com",
                role=ROLE_RECEPTIONIST,
            )
            db.commit()

            admin_token = create_access_token({"sub": admin.id, "org_id": org_id})
            target_user_id = target_user.id

        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/admin/users/{target_user_id}/role",
                json={"role": ROLE_CASE_MANAGER},
                headers=_auth_header(admin_token),
            )
            assert response.status_code == 200
            assert response.json()["role"] == ROLE_CASE_MANAGER

        with TestingSessionLocal() as db:
            membership = db.execute(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == org_id,
                    OrganizationMembership.user_id == target_user_id,
                )
            ).scalar_one()
            assert membership.role == ROLE_CASE_MANAGER
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_updated_role_permissions_are_enforced(tmp_path) -> None:
    database_file = tmp_path / "phase1_rbac_permissions.sqlite"
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
            org = Organization(name="Permission Enforced Org")
            db.add(org)
            db.flush()
            org_id = org.id

            admin = _create_user_membership(
                db,
                organization_id=org_id,
                email="admin-perms@example.com",
                role=ROLE_ADMIN,
            )
            receptionist = _create_user_membership(
                db,
                organization_id=org_id,
                email="reception-perms@example.com",
                role=ROLE_RECEPTIONIST,
            )
            db.commit()
            admin_token = create_access_token({"sub": admin.id, "org_id": org_id})
            receptionist_token = create_access_token({"sub": receptionist.id, "org_id": org_id})

        with TestClient(app) as client:
            denied = client.get(
                "/api/v1/admin/organization/settings",
                headers=_auth_header(receptionist_token),
            )
            assert denied.status_code == 403

            roles = client.get(
                "/api/v1/admin/roles",
                headers=_auth_header(admin_token),
            )
            assert roles.status_code == 200
            receptionist_role = next(
                row for row in roles.json() if row["key"] == ROLE_RECEPTIONIST
            )
            next_permissions = sorted(
                set(receptionist_role["permissions"]) | {"admin:org_settings"}
            )

            updated = client.put(
                f"/api/v1/admin/roles/{ROLE_RECEPTIONIST}/permissions",
                json={"permissions": next_permissions},
                headers=_auth_header(admin_token),
            )
            assert updated.status_code == 200
            assert "admin:org_settings" in updated.json()["permissions"]

            allowed = client.get(
                "/api/v1/admin/organization/settings",
                headers=_auth_header(receptionist_token),
            )
            assert allowed.status_code == 200
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
