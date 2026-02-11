from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.rbac import (
    ROLE_ADMIN,
    ROLE_BILLING,
    ROLE_CASE_MANAGER,
    ROLE_COUNSELOR,
    ROLE_RECEPTIONIST,
    ROLE_SUD_SUPERVISOR,
)
from app.core.security import create_access_token
from app.core.time import utc_now
from app.db.base import Base
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.task import Task
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


def _create_task(
    db,
    *,
    organization_id: str,
    title: str,
    created_by_user_id: str,
    assigned_to_user_id: str | None = None,
    assigned_team_id: str | None = None,
) -> Task:
    row = Task(
        organization_id=organization_id,
        title=title,
        description=None,
        status="open",
        priority="normal",
        due_at=utc_now() + timedelta(days=1),
        completed_at=None,
        created_by_user_id=created_by_user_id,
        assigned_to_user_id=assigned_to_user_id,
        assigned_team_id=assigned_team_id,
        related_type=None,
        related_id=None,
        tags_json="[]",
    )
    db.add(row)
    db.flush()
    return row


def test_receptionist_cannot_list_all_tasks(tmp_path) -> None:
    database_file = tmp_path / "tasks_receptionist_scope.sqlite"
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
            org = Organization(name="Tasks Org")
            db.add(org)
            db.flush()
            receptionist = _create_user_membership(
                db,
                organization_id=org.id,
                email="reception.tasks@example.com",
                role=ROLE_RECEPTIONIST,
            )
            _create_task(
                db,
                organization_id=org.id,
                title="Task A",
                created_by_user_id=receptionist.id,
                assigned_to_user_id=receptionist.id,
            )
            db.commit()
            token = create_access_token({"sub": receptionist.id, "org_id": org.id})

        with TestClient(app) as client:
            response = client.get("/api/v1/tasks?scope=all", headers=_auth_header(token))
            assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_admin_can_list_all_tasks(tmp_path) -> None:
    database_file = tmp_path / "tasks_admin_scope.sqlite"
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
            org = Organization(name="Tasks Admin Org")
            db.add(org)
            db.flush()
            admin = _create_user_membership(
                db,
                organization_id=org.id,
                email="admin.tasks@example.com",
                role=ROLE_ADMIN,
            )
            counselor = _create_user_membership(
                db,
                organization_id=org.id,
                email="counselor.tasks@example.com",
                role=ROLE_COUNSELOR,
            )
            _create_task(
                db,
                organization_id=org.id,
                title="Task One",
                created_by_user_id=admin.id,
                assigned_to_user_id=admin.id,
                assigned_team_id="admissions",
            )
            _create_task(
                db,
                organization_id=org.id,
                title="Task Two",
                created_by_user_id=admin.id,
                assigned_to_user_id=counselor.id,
                assigned_team_id="clinical",
            )
            db.commit()
            token = create_access_token({"sub": admin.id, "org_id": org.id})

        with TestClient(app) as client:
            response = client.get("/api/v1/tasks?scope=all", headers=_auth_header(token))
            assert response.status_code == 200
            payload = response.json()
            assert payload["total"] == 2
            assert len(payload["items"]) == 2
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_supervisor_can_list_team_tasks(tmp_path) -> None:
    database_file = tmp_path / "tasks_supervisor_scope.sqlite"
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
            org = Organization(name="Tasks Supervisor Org")
            db.add(org)
            db.flush()
            supervisor = _create_user_membership(
                db,
                organization_id=org.id,
                email="supervisor.tasks@example.com",
                role=ROLE_SUD_SUPERVISOR,
            )
            counselor = _create_user_membership(
                db,
                organization_id=org.id,
                email="clinical.tasks@example.com",
                role=ROLE_COUNSELOR,
            )
            billing = _create_user_membership(
                db,
                organization_id=org.id,
                email="billing.tasks@example.com",
                role=ROLE_BILLING,
            )

            team_task = _create_task(
                db,
                organization_id=org.id,
                title="Clinical Team Task",
                created_by_user_id=supervisor.id,
                assigned_to_user_id=counselor.id,
                assigned_team_id="clinical",
            )
            team_task_id = team_task.id
            _create_task(
                db,
                organization_id=org.id,
                title="Billing Task",
                created_by_user_id=billing.id,
                assigned_to_user_id=billing.id,
                assigned_team_id="billing",
            )
            db.commit()
            token = create_access_token({"sub": supervisor.id, "org_id": org.id})

        with TestClient(app) as client:
                response = client.get("/api/v1/tasks?scope=team", headers=_auth_header(token))
                assert response.status_code == 200
                payload = response.json()
                ids = {item["id"] for item in payload["items"]}
                assert team_task_id in ids
                assert len(ids) == 1
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_assignment_requires_tasks_assign(tmp_path) -> None:
    database_file = tmp_path / "tasks_assign_perm.sqlite"
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
            org = Organization(name="Tasks Assign Org")
            db.add(org)
            db.flush()
            counselor = _create_user_membership(
                db,
                organization_id=org.id,
                email="counselor.assign@example.com",
                role=ROLE_COUNSELOR,
            )
            other_user = _create_user_membership(
                db,
                organization_id=org.id,
                email="other.assign@example.com",
                role=ROLE_CASE_MANAGER,
            )
            db.commit()
            token = create_access_token({"sub": counselor.id, "org_id": org.id})
            other_user_id = other_user.id

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/tasks",
                json={
                    "title": "Counselor cannot assign others",
                    "assigned_to_user_id": other_user_id,
                },
                headers=_auth_header(token),
            )
            assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_task_org_scoping_enforced(tmp_path) -> None:
    database_file = tmp_path / "tasks_org_scope.sqlite"
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
            org_a = Organization(name="Tasks Org A")
            org_b = Organization(name="Tasks Org B")
            db.add(org_a)
            db.add(org_b)
            db.flush()

            admin_a = _create_user_membership(
                db,
                organization_id=org_a.id,
                email="admin.scope.a@example.com",
                role=ROLE_ADMIN,
            )
            admin_b = _create_user_membership(
                db,
                organization_id=org_b.id,
                email="admin.scope.b@example.com",
                role=ROLE_ADMIN,
            )
            task_a = _create_task(
                db,
                organization_id=org_a.id,
                title="Scoped Task",
                created_by_user_id=admin_a.id,
                assigned_to_user_id=admin_a.id,
                assigned_team_id="admissions",
            )
            db.commit()

            token_b = create_access_token({"sub": admin_b.id, "org_id": org_b.id})
            task_a_id = task_a.id

        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/tasks/{task_a_id}",
                headers=_auth_header(token_b),
            )
            assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
