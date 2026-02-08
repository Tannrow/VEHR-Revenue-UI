from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN
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


def _setup_test_session(tmp_path, db_name: str):
    database_file = tmp_path / db_name
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

    return engine, TestingSessionLocal, override_get_db


def test_sign_note_auto_creates_encounter(tmp_path) -> None:
    engine, TestingSessionLocal, override_get_db = _setup_test_session(
        tmp_path,
        "notes_sign_encounter.sqlite",
    )
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestingSessionLocal() as db:
            org = Organization(name="Notes Org")
            db.add(org)
            db.flush()

            admin = User(
                email="admin-notes@example.com",
                full_name="Admin Notes",
                hashed_password=DUMMY_HASH,
                is_active=True,
            )
            db.add(admin)
            db.flush()

            db.add(
                OrganizationMembership(
                    organization_id=org.id,
                    user_id=admin.id,
                    role=ROLE_ADMIN,
                )
            )

            patient = Patient(
                organization_id=org.id,
                first_name="Nora",
                last_name="Note",
                dob=date(1990, 1, 1),
                phone="555-123-2222",
                email="nora@example.com",
            )
            db.add(patient)
            db.commit()

            token = create_access_token({"sub": admin.id, "org_id": org.id})
            patient_id = patient.id

        with TestClient(app) as client:
            service_res = client.post(
                "/api/v1/services",
                json={
                    "name": "SUD IOP",
                    "code": "SUD_IOP",
                    "category": "sud",
                    "sort_order": 1,
                },
                headers=_auth_header(token),
            )
            assert service_res.status_code == 201
            service_id = service_res.json()["id"]

            note_res = client.post(
                f"/api/v1/patients/{patient_id}/notes",
                json={
                    "primary_service_id": service_id,
                    "body": "Draft clinical note",
                    "visibility": "clinical_only",
                },
                headers=_auth_header(token),
            )
            assert note_res.status_code == 201
            note_id = note_res.json()["id"]
            assert note_res.json()["status"] == "draft"
            assert note_res.json()["encounter_id"] is None

            signed_res = client.post(
                f"/api/v1/notes/{note_id}/sign",
                json={},
                headers=_auth_header(token),
            )
            assert signed_res.status_code == 200
            signed_payload = signed_res.json()
            assert signed_payload["status"] == "signed"
            assert signed_payload["encounter_id"] is not None
            assert signed_payload["signed_at"] is not None
            assert signed_payload["signed_by_user_id"] is not None

            encounter_res = client.get(
                f"/api/v1/encounters/{signed_payload['encounter_id']}",
                headers=_auth_header(token),
            )
            assert encounter_res.status_code == 200
            assert encounter_res.json()["patient_id"] == patient_id
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_unsigned_note_requirement_refreshes(tmp_path) -> None:
    engine, TestingSessionLocal, override_get_db = _setup_test_session(
        tmp_path,
        "notes_requirements.sqlite",
    )
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestingSessionLocal() as db:
            org = Organization(name="Req Notes Org")
            db.add(org)
            db.flush()

            admin = User(
                email="admin-req-notes@example.com",
                full_name="Admin Req Notes",
                hashed_password=DUMMY_HASH,
                is_active=True,
            )
            db.add(admin)
            db.flush()

            db.add(
                OrganizationMembership(
                    organization_id=org.id,
                    user_id=admin.id,
                    role=ROLE_ADMIN,
                )
            )

            patient = Patient(
                organization_id=org.id,
                first_name="Rhea",
                last_name="Requirement",
                dob=date(1995, 5, 5),
                phone="555-777-8888",
                email="rhea@example.com",
            )
            db.add(patient)
            db.commit()

            token = create_access_token({"sub": admin.id, "org_id": org.id})
            patient_id = patient.id

        with TestClient(app) as client:
            episode = client.post(
                f"/api/v1/patients/{patient_id}/episodes",
                json={
                    "admit_date": "2026-02-08",
                    "primary_service_category": "sud",
                },
                headers=_auth_header(token),
            )
            assert episode.status_code == 201

            service_res = client.post(
                "/api/v1/services",
                json={
                    "name": "SUD OP",
                    "code": "SUD_OP",
                    "category": "sud",
                    "sort_order": 1,
                },
                headers=_auth_header(token),
            )
            assert service_res.status_code == 201
            service_id = service_res.json()["id"]

            note_res = client.post(
                f"/api/v1/patients/{patient_id}/notes",
                json={
                    "primary_service_id": service_id,
                    "body": "Unsigned note",
                },
                headers=_auth_header(token),
            )
            assert note_res.status_code == 201
            note_id = note_res.json()["id"]

            refreshed = client.post(
                f"/api/v1/patients/{patient_id}/requirements/refresh",
                headers=_auth_header(token),
            )
            assert refreshed.status_code == 200
            by_type = {row["requirement_type"]: row for row in refreshed.json()}
            assert by_type["unsigned_note"]["status"] == "open"

            signed = client.post(
                f"/api/v1/notes/{note_id}/sign",
                json={},
                headers=_auth_header(token),
            )
            assert signed.status_code == 200

            refreshed_again = client.post(
                f"/api/v1/patients/{patient_id}/requirements/refresh",
                headers=_auth_header(token),
            )
            assert refreshed_again.status_code == 200
            by_type = {row["requirement_type"]: row for row in refreshed_again.json()}
            assert by_type["unsigned_note"]["status"] == "resolved"
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
