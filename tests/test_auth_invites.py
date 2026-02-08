from __future__ import annotations

import hashlib
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN, ROLE_CASE_MANAGER, ROLE_COUNSELOR
from app.core.security import create_access_token, hash_password
from app.core.time import utc_now
from app.db.base import Base
from app.db.models.audit_event import AuditEvent
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.password_reset_token import PasswordResetToken
from app.db.models.user import User
from app.db.session import get_db
from app.main import app


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_user_membership(db, *, organization_id: str, email: str, role: str, password: str) -> User:
    user = User(
        email=email,
        full_name=email.split("@", 1)[0],
        hashed_password=hash_password(password),
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


def test_invite_acceptance_and_role_assignment_rules(tmp_path) -> None:
    database_file = tmp_path / "auth_invites.sqlite"
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
            org = Organization(name="Invite Org")
            db.add(org)
            db.flush()
            admin = _create_user_membership(
                db,
                organization_id=org.id,
                email="admin@example.com",
                role=ROLE_ADMIN,
                password="AdminPass123!",
            )
            db.commit()
            admin_token = create_access_token({"sub": admin.id, "org_id": org.id})

        with TestClient(app) as client:
            invalid_allowed_roles = client.post(
                "/api/v1/admin/invites",
                json={"email": "newuser@example.com", "allowed_roles": [ROLE_ADMIN]},
                headers=_auth_header(admin_token),
            )
            assert invalid_allowed_roles.status_code == 400

            created = client.post(
                "/api/v1/admin/invites",
                json={"email": "newuser@example.com"},
                headers=_auth_header(admin_token),
            )
            assert created.status_code == 201
            invite_id = created.json()["id"]

            with TestingSessionLocal() as db:
                invite = db.execute(select(_models.Invite).where(_models.Invite.id == invite_id)).scalar_one()
                raw_token = "known-invite-token"
                invite.token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
                db.add(invite)
                db.commit()

            accepted = client.post(
                "/api/v1/auth/accept-invite",
                json={
                    "token": raw_token,
                    "role": ROLE_COUNSELOR,
                    "full_name": "New User",
                    "password": "NewUserPass123!",
                },
            )
            assert accepted.status_code == 200
            new_user_id = accepted.json()["user_id"]

            role_update = client.patch(
                f"/api/v1/admin/users/{new_user_id}/role",
                json={"role": ROLE_CASE_MANAGER},
                headers=_auth_header(admin_token),
            )
            assert role_update.status_code == 200
            assert role_update.json()["role"] == ROLE_CASE_MANAGER

            with TestingSessionLocal() as db:
                actions = [
                    row.action
                    for row in db.execute(select(AuditEvent)).scalars().all()
                ]
                assert "invite.created" in actions
                assert "invite.accepted" in actions
                assert "user.role_updated" in actions
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_invite_resend_and_revoke_flow(tmp_path) -> None:
    database_file = tmp_path / "auth_invites_revoke.sqlite"
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
            org = Organization(name="Invite Flow Org")
            db.add(org)
            db.flush()
            admin = _create_user_membership(
                db,
                organization_id=org.id,
                email="admin-flow@example.com",
                role=ROLE_ADMIN,
                password="AdminPass123!",
            )
            db.commit()
            admin_token = create_access_token({"sub": admin.id, "org_id": org.id})

        with TestClient(app) as client:
            created = client.post(
                "/api/v1/admin/invites",
                json={"email": "flow-user@example.com"},
                headers=_auth_header(admin_token),
            )
            assert created.status_code == 201
            invite_id = created.json()["id"]

            resent = client.post(
                f"/api/v1/admin/invites/{invite_id}/resend",
                headers=_auth_header(admin_token),
            )
            assert resent.status_code == 200
            assert resent.json()["status"] == "pending"

            revoked = client.post(
                f"/api/v1/admin/invites/{invite_id}/revoke",
                headers=_auth_header(admin_token),
            )
            assert revoked.status_code == 200
            assert revoked.json()["status"] == "revoked"

            resend_revoked = client.post(
                f"/api/v1/admin/invites/{invite_id}/resend",
                headers=_auth_header(admin_token),
            )
            assert resend_revoked.status_code == 400
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_change_password_and_reset_password(tmp_path) -> None:
    database_file = tmp_path / "auth_password_flows.sqlite"
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
            org = Organization(name="Password Org")
            db.add(org)
            db.flush()
            user = _create_user_membership(
                db,
                organization_id=org.id,
                email="password-user@example.com",
                role=ROLE_COUNSELOR,
                password="OldPass123!",
            )
            db.commit()
            token = create_access_token({"sub": user.id, "org_id": org.id})
            user_id = user.id

        with TestClient(app) as client:
            changed = client.post(
                "/api/v1/auth/change-password",
                json={"current_password": "OldPass123!", "new_password": "NewPass123!"},
                headers=_auth_header(token),
            )
            assert changed.status_code == 200

            old_login = client.post(
                "/api/v1/auth/login",
                json={"email": "password-user@example.com", "password": "OldPass123!"},
            )
            assert old_login.status_code == 401

            new_login = client.post(
                "/api/v1/auth/login",
                json={"email": "password-user@example.com", "password": "NewPass123!"},
            )
            assert new_login.status_code == 200

            requested = client.post(
                "/api/v1/auth/request-password-reset",
                json={"email": "password-user@example.com"},
            )
            assert requested.status_code == 200

            known_reset_token = "known-reset-token"
            with TestingSessionLocal() as db:
                db.add(
                    PasswordResetToken(
                        user_id=user_id,
                        token_hash=hashlib.sha256(known_reset_token.encode("utf-8")).hexdigest(),
                        expires_at=utc_now() + timedelta(minutes=30),
                    )
                )
                db.commit()

            reset_done = client.post(
                "/api/v1/auth/reset-password",
                json={"token": known_reset_token, "new_password": "ResetPass123!"},
            )
            assert reset_done.status_code == 200

            reset_login = client.post(
                "/api/v1/auth/login",
                json={"email": "password-user@example.com", "password": "ResetPass123!"},
            )
            assert reset_login.status_code == 200
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
