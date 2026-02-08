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
from app.db.models.patient import Patient
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


def test_patient_chart_endpoints_are_tenant_scoped(tmp_path) -> None:
    database_file = tmp_path / "patient_chart_tenant.sqlite"
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
            org_a = Organization(name="Org A")
            org_b = Organization(name="Org B")
            db.add(org_a)
            db.add(org_b)
            db.flush()

            admin_a = _create_user_membership(
                db,
                organization_id=org_a.id,
                email="admin-a@example.com",
                role=ROLE_ADMIN,
            )
            admin_b = _create_user_membership(
                db,
                organization_id=org_b.id,
                email="admin-b@example.com",
                role=ROLE_ADMIN,
            )
            patient_a = Patient(
                organization_id=org_a.id,
                first_name="Alice",
                last_name="Scoped",
            )
            db.add(patient_a)
            db.commit()

            token_a = create_access_token({"sub": admin_a.id, "org_id": org_a.id})
            token_b = create_access_token({"sub": admin_b.id, "org_id": org_b.id})
            patient_a_id = patient_a.id

        with TestClient(app) as client:
            created = client.post(
                f"/api/v1/patients/{patient_a_id}/episodes",
                json={
                    "admit_date": "2026-02-08",
                    "primary_service_category": "sud",
                },
                headers=_auth_header(token_a),
            )
            assert created.status_code == 201
            episode_id = created.json()["id"]

            org_b_list = client.get(
                f"/api/v1/patients/{patient_a_id}/episodes",
                headers=_auth_header(token_b),
            )
            assert org_b_list.status_code == 404

            org_b_patch = client.patch(
                f"/api/v1/episodes/{episode_id}",
                json={"status": "discharged", "discharge_date": "2026-02-09"},
                headers=_auth_header(token_b),
            )
            assert org_b_patch.status_code == 404
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_episode_lifecycle_and_treatment_stage(tmp_path) -> None:
    database_file = tmp_path / "patient_chart_lifecycle.sqlite"
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
            org = Organization(name="Lifecycle Org")
            db.add(org)
            db.flush()
            admin = _create_user_membership(
                db,
                organization_id=org.id,
                email="admin@example.com",
                role=ROLE_ADMIN,
            )
            patient = Patient(
                organization_id=org.id,
                first_name="Tanner",
                last_name="Patient",
            )
            db.add(patient)
            db.commit()
            token = create_access_token({"sub": admin.id, "org_id": org.id})
            patient_id = patient.id

        with TestClient(app) as client:
            first_episode = client.post(
                f"/api/v1/patients/{patient_id}/episodes",
                json={
                    "admit_date": "2026-02-01",
                    "primary_service_category": "sud",
                },
                headers=_auth_header(token),
            )
            assert first_episode.status_code == 201
            first_episode_id = first_episode.json()["id"]

            second_active_denied = client.post(
                f"/api/v1/patients/{patient_id}/episodes",
                json={
                    "admit_date": "2026-02-02",
                    "primary_service_category": "sud",
                },
                headers=_auth_header(token),
            )
            assert second_active_denied.status_code == 409

            discharge = client.patch(
                f"/api/v1/episodes/{first_episode_id}",
                json={
                    "status": "discharged",
                    "discharge_date": "2026-02-05",
                    "discharge_disposition": "step_down",
                },
                headers=_auth_header(token),
            )
            assert discharge.status_code == 200
            assert discharge.json()["status"] == "discharged"

            second_episode = client.post(
                f"/api/v1/patients/{patient_id}/episodes",
                json={
                    "admit_date": "2026-02-06",
                    "primary_service_category": "mh",
                },
                headers=_auth_header(token),
            )
            assert second_episode.status_code == 201

            stage = client.get(
                f"/api/v1/patients/{patient_id}/treatment-stage",
                headers=_auth_header(token),
            )
            assert stage.status_code == 200
            assert stage.json()["stage"] == "intake_started"

            stage_update = client.post(
                f"/api/v1/patients/{patient_id}/treatment-stage",
                json={"stage": "active_treatment", "reason": "Care plan signed"},
                headers=_auth_header(token),
            )
            assert stage_update.status_code == 200
            assert stage_update.json()["stage"] == "active_treatment"

            stage_events = client.get(
                f"/api/v1/patients/{patient_id}/treatment-stage/events",
                headers=_auth_header(token),
            )
            assert stage_events.status_code == 200
            assert len(stage_events.json()) >= 1
            assert stage_events.json()[0]["to_stage"] in {"intake_started", "active_treatment"}
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_requirements_refresh_and_care_team_assignment(tmp_path) -> None:
    database_file = tmp_path / "patient_chart_requirements.sqlite"
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
            org = Organization(name="Requirements Org")
            db.add(org)
            db.flush()
            admin = _create_user_membership(
                db,
                organization_id=org.id,
                email="admin-req@example.com",
                role=ROLE_ADMIN,
            )
            clinician = _create_user_membership(
                db,
                organization_id=org.id,
                email="clinician@example.com",
                role=ROLE_CLINICIAN,
            )
            patient = Patient(
                organization_id=org.id,
                first_name="NoDOB",
                last_name="NoContact",
                dob=None,
                phone=None,
                email=None,
            )
            db.add(patient)
            db.commit()
            token = create_access_token({"sub": admin.id, "org_id": org.id})
            clinician_id = clinician.id
            patient_id = patient.id

        with TestClient(app) as client:
            episode = client.post(
                f"/api/v1/patients/{patient_id}/episodes",
                json={
                    "admit_date": "2026-02-08",
                    "primary_service_category": "intake",
                },
                headers=_auth_header(token),
            )
            assert episode.status_code == 201
            episode_id = episode.json()["id"]

            assigned = client.post(
                f"/api/v1/patients/{patient_id}/care-team",
                json={
                    "episode_id": episode_id,
                    "role": "counselor",
                    "user_id": clinician_id,
                },
                headers=_auth_header(token),
            )
            assert assigned.status_code == 201
            assert assigned.json()["role"] == "counselor"

            refreshed = client.post(
                f"/api/v1/patients/{patient_id}/requirements/refresh",
                headers=_auth_header(token),
            )
            assert refreshed.status_code == 200
            req_by_type = {item["requirement_type"]: item for item in refreshed.json()}
            assert req_by_type["missing_demographics"]["status"] == "open"

            with TestingSessionLocal() as db:
                row = db.get(Patient, patient_id)
                row.dob = date(1990, 1, 1)
                row.phone = "555-123-4567"
                db.add(row)
                db.commit()

            refreshed_again = client.post(
                f"/api/v1/patients/{patient_id}/requirements/refresh",
                headers=_auth_header(token),
            )
            assert refreshed_again.status_code == 200
            req_by_type = {item["requirement_type"]: item for item in refreshed_again.json()}
            assert req_by_type["missing_demographics"]["status"] == "resolved"
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
