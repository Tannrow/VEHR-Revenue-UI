from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN, ROLE_CLINICIAN
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


def _create_user_with_membership(
    db,
    *,
    org_name: str,
    email: str,
    role: str,
) -> tuple[Organization, User]:
    org = Organization(name=org_name)
    db.add(org)
    db.flush()

    user = User(
        email=email,
        full_name=email.split("@", 1)[0],
        hashed_password=DUMMY_HASH,
        is_active=True,
    )
    db.add(user)
    db.flush()

    membership = OrganizationMembership(
        organization_id=org.id,
        user_id=user.id,
        role=role,
    )
    db.add(membership)
    db.commit()
    db.refresh(org)
    db.refresh(user)
    return org, user


def test_services_and_enrollments_are_tenant_scoped(tmp_path) -> None:
    database_file = tmp_path / "phase1_tenant_scope.sqlite"
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
            org_a, user_a = _create_user_with_membership(
                db,
                org_name="Org A",
                email="admin-a@example.com",
                role=ROLE_ADMIN,
            )
            org_b, user_b = _create_user_with_membership(
                db,
                org_name="Org B",
                email="admin-b@example.com",
                role=ROLE_ADMIN,
            )

            token_a = create_access_token({"sub": user_a.id, "org_id": org_a.id})
            token_b = create_access_token({"sub": user_b.id, "org_id": org_b.id})

        with TestClient(app) as client:
            patient_res = client.post(
                "/api/v1/patients",
                json={"first_name": "Alice", "last_name": "Scoped"},
                headers=_auth_header(token_a),
            )
            assert patient_res.status_code == 201
            patient_id = patient_res.json()["id"]

            service_res = client.post(
                "/api/v1/services",
                json={
                    "name": "SUD IOP",
                    "code": "SUD_IOP",
                    "category": "sud",
                    "is_active": True,
                    "sort_order": 1,
                },
                headers=_auth_header(token_a),
            )
            assert service_res.status_code == 201
            service_id = service_res.json()["id"]

            org_b_services = client.get("/api/v1/services", headers=_auth_header(token_b))
            assert org_b_services.status_code == 200
            assert all(item["id"] != service_id for item in org_b_services.json())

            org_b_patch = client.patch(
                f"/api/v1/services/{service_id}",
                json={"name": "cross-tenant-update"},
                headers=_auth_header(token_b),
            )
            assert org_b_patch.status_code == 404

            org_b_create_enrollment = client.post(
                f"/api/v1/patients/{patient_id}/enrollments",
                json={
                    "service_id": service_id,
                    "status": "active",
                    "start_date": "2026-02-08",
                },
                headers=_auth_header(token_b),
            )
            assert org_b_create_enrollment.status_code == 404
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_sud_exclusivity_is_enforced(tmp_path) -> None:
    database_file = tmp_path / "phase1_sud_exclusivity.sqlite"
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
            org, user = _create_user_with_membership(
                db,
                org_name="SUD Org",
                email="sud-admin@example.com",
                role=ROLE_ADMIN,
            )
            token = create_access_token({"sub": user.id, "org_id": org.id})

        with TestClient(app) as client:
            patient_res = client.post(
                "/api/v1/patients",
                json={"first_name": "Sam", "last_name": "Recovery"},
                headers=_auth_header(token),
            )
            assert patient_res.status_code == 201
            patient_id = patient_res.json()["id"]

            sud_service_1 = client.post(
                "/api/v1/services",
                json={"name": "SUD IOP", "code": "SUD_IOP", "category": "sud", "sort_order": 1},
                headers=_auth_header(token),
            )
            assert sud_service_1.status_code == 201
            sud_service_1_id = sud_service_1.json()["id"]

            sud_service_2 = client.post(
                "/api/v1/services",
                json={"name": "SUD PHP", "code": "SUD_PHP", "category": "sud", "sort_order": 2},
                headers=_auth_header(token),
            )
            assert sud_service_2.status_code == 201
            sud_service_2_id = sud_service_2.json()["id"]

            mh_service = client.post(
                "/api/v1/services",
                json={"name": "MH Counseling", "code": "MH_COUNSEL", "category": "mh", "sort_order": 3},
                headers=_auth_header(token),
            )
            assert mh_service.status_code == 201
            mh_service_id = mh_service.json()["id"]

            first_sud = client.post(
                f"/api/v1/patients/{patient_id}/enrollments",
                json={
                    "service_id": sud_service_1_id,
                    "status": "active",
                    "start_date": "2026-02-01",
                },
                headers=_auth_header(token),
            )
            assert first_sud.status_code == 201
            first_sud_id = first_sud.json()["id"]

            conflicting_sud = client.post(
                f"/api/v1/patients/{patient_id}/enrollments",
                json={
                    "service_id": sud_service_2_id,
                    "status": "active",
                    "start_date": "2026-02-05",
                },
                headers=_auth_header(token),
            )
            assert conflicting_sud.status_code == 409

            mh_active = client.post(
                f"/api/v1/patients/{patient_id}/enrollments",
                json={
                    "service_id": mh_service_id,
                    "status": "active",
                    "start_date": "2026-02-05",
                },
                headers=_auth_header(token),
            )
            assert mh_active.status_code == 201

            close_first_sud = client.patch(
                f"/api/v1/enrollments/{first_sud_id}",
                json={"status": "discharged", "end_date": "2026-02-10"},
                headers=_auth_header(token),
            )
            assert close_first_sud.status_code == 200

            later_sud = client.post(
                f"/api/v1/patients/{patient_id}/enrollments",
                json={
                    "service_id": sud_service_2_id,
                    "status": "active",
                    "start_date": "2026-02-11",
                },
                headers=_auth_header(token),
            )
            assert later_sud.status_code == 201
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_enrollment_lifecycle_and_overlap_rules(tmp_path) -> None:
    database_file = tmp_path / "phase1_enrollment_lifecycle.sqlite"
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
            org, admin = _create_user_with_membership(
                db,
                org_name="Lifecycle Org",
                email="lifecycle-admin@example.com",
                role=ROLE_ADMIN,
            )

            staff = User(
                email="lifecycle-clinician@example.com",
                full_name="Lifecycle Clinician",
                hashed_password=DUMMY_HASH,
                is_active=True,
            )
            db.add(staff)
            db.flush()
            db.add(
                OrganizationMembership(
                    organization_id=org.id,
                    user_id=staff.id,
                    role=ROLE_CLINICIAN,
                )
            )
            db.commit()

            token = create_access_token({"sub": admin.id, "org_id": org.id})
            staff_id = staff.id

        with TestClient(app) as client:
            patient_res = client.post(
                "/api/v1/patients",
                json={"first_name": "Liam", "last_name": "Lifecycle"},
                headers=_auth_header(token),
            )
            assert patient_res.status_code == 201
            patient_id = patient_res.json()["id"]

            service_res = client.post(
                "/api/v1/services",
                json={"name": "Intake", "code": "INTAKE", "category": "intake", "sort_order": 1},
                headers=_auth_header(token),
            )
            assert service_res.status_code == 201
            service_id = service_res.json()["id"]

            first = client.post(
                f"/api/v1/patients/{patient_id}/enrollments",
                json={
                    "service_id": service_id,
                    "status": "active",
                    "start_date": "2026-01-01",
                },
                headers=_auth_header(token),
            )
            assert first.status_code == 201
            first_id = first.json()["id"]

            overlap = client.post(
                f"/api/v1/patients/{patient_id}/enrollments",
                json={
                    "service_id": service_id,
                    "status": "active",
                    "start_date": "2026-01-05",
                },
                headers=_auth_header(token),
            )
            assert overlap.status_code == 409

            close_first = client.patch(
                f"/api/v1/enrollments/{first_id}",
                json={"status": "discharged", "end_date": "2026-01-10"},
                headers=_auth_header(token),
            )
            assert close_first.status_code == 200

            second = client.post(
                f"/api/v1/patients/{patient_id}/enrollments",
                json={
                    "service_id": service_id,
                    "status": "active",
                    "start_date": "2026-01-11",
                },
                headers=_auth_header(token),
            )
            assert second.status_code == 201
            second_id = second.json()["id"]

            update_second = client.patch(
                f"/api/v1/enrollments/{second_id}",
                json={
                    "status": "paused",
                    "assigned_staff_user_id": staff_id,
                    "reporting_enabled": True,
                },
                headers=_auth_header(token),
            )
            assert update_second.status_code == 200
            payload = update_second.json()
            assert payload["status"] == "paused"
            assert payload["assigned_staff_user_id"] == staff_id
            assert payload["reporting_enabled"] is True

            listed = client.get(
                f"/api/v1/patients/{patient_id}/enrollments",
                headers=_auth_header(token),
            )
            assert listed.status_code == 200
            enrollment_by_id = {row["id"]: row for row in listed.json()}
            assert enrollment_by_id[first_id]["status"] == "discharged"
            assert enrollment_by_id[first_id]["end_date"] == date(2026, 1, 10).isoformat()
            assert enrollment_by_id[second_id]["status"] == "paused"
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
