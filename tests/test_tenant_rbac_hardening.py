from __future__ import annotations


import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN, ROLE_STAFF
from app.core.security import create_access_token
from app.db.base import Base
from app.db.models.encounter import Encounter
from app.db.models.form_template import FormTemplate
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.patient import Patient
from app.db.models.user import User
from app.db.session import get_db
from app.main import app
from app.core.time import utc_now


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


@pytest.fixture()
def session_factory(tmp_path):
    database_file = tmp_path / "tenant_rbac.sqlite"
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
        yield TestingSessionLocal
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(session_factory):
    with TestClient(app) as test_client:
        yield test_client


def test_cross_tenant_patient_and_encounter_access_is_blocked(client: TestClient, session_factory) -> None:
    with session_factory() as db:
        org_a, user_a = _create_user_with_membership(
            db,
            org_name="OrgA",
            email="orga-admin@example.com",
            role=ROLE_ADMIN,
        )
        org_b, user_b = _create_user_with_membership(
            db,
            org_name="OrgB",
            email="orgb-admin@example.com",
            role=ROLE_ADMIN,
        )

        patient_a = Patient(
            organization_id=org_a.id,
            first_name="Alice",
            last_name="A",
            dob=None,
            phone=None,
            email=None,
        )
        db.add(patient_a)
        db.flush()

        encounter_a = Encounter(
            organization_id=org_a.id,
            patient_id=patient_a.id,
            encounter_type="intake",
            start_time=utc_now(),
            end_time=None,
            clinician=None,
            location=None,
            modality=None,
        )
        db.add(encounter_a)
        db.commit()

        patient_a_id = patient_a.id
        encounter_a_id = encounter_a.id
        token_a = create_access_token({"sub": user_a.id, "org_id": org_a.id})
        token_b = create_access_token({"sub": user_b.id, "org_id": org_b.id})

    org_a_list = client.get("/api/v1/patients", headers=_auth_header(token_a))
    assert org_a_list.status_code == 200
    assert any(item["id"] == patient_a_id for item in org_a_list.json())

    org_b_list = client.get("/api/v1/patients", headers=_auth_header(token_b))
    assert org_b_list.status_code == 200
    assert all(item["id"] != patient_a_id for item in org_b_list.json())

    org_b_get_patient = client.get(f"/api/v1/patients/{patient_a_id}", headers=_auth_header(token_b))
    assert org_b_get_patient.status_code == 404

    org_b_get_encounter = client.get(
        f"/api/v1/encounters/{encounter_a_id}",
        headers=_auth_header(token_b),
    )
    assert org_b_get_encounter.status_code == 404

    org_b_list_encounters = client.get(
        f"/api/v1/patients/{patient_a_id}/encounters",
        headers=_auth_header(token_b),
    )
    assert org_b_list_encounters.status_code == 200
    assert org_b_list_encounters.json() == []


def test_publish_template_requires_forms_write_permission(client: TestClient, session_factory) -> None:
    with session_factory() as db:
        org, admin_user = _create_user_with_membership(
            db,
            org_name="PublishOrg",
            email="publish-admin@example.com",
            role=ROLE_ADMIN,
        )

        staff_user = User(
            email="publish-staff@example.com",
            full_name="publish-staff",
            hashed_password=DUMMY_HASH,
            is_active=True,
        )
        db.add(staff_user)
        db.flush()
        staff_membership = OrganizationMembership(
            organization_id=org.id,
            user_id=staff_user.id,
            role=ROLE_STAFF,
        )
        db.add(staff_membership)

        template = FormTemplate(
            organization_id=org.id,
            name="Initial Intake",
            version=1,
            status="draft",
            schema_json='{"type":"object","required":["note"],"properties":{"note":{"type":"string"}}}',
        )
        db.add(template)
        db.commit()

        template_id = template.id
        admin_token = create_access_token({"sub": admin_user.id, "org_id": org.id})
        staff_token = create_access_token({"sub": staff_user.id, "org_id": org.id})

    denied = client.post(
        f"/api/v1/forms/templates/{template_id}/publish",
        json={},
        headers=_auth_header(staff_token),
    )
    assert denied.status_code == 403

    allowed = client.post(
        f"/api/v1/forms/templates/{template_id}/publish",
        json={},
        headers=_auth_header(admin_token),
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "published"


def test_upload_presign_enforces_rbac_and_tenant_prefix(client: TestClient, session_factory) -> None:
    with session_factory() as db:
        org_a, _admin_a = _create_user_with_membership(
            db,
            org_name="OrgA Uploads",
            email="orga-uploads-admin@example.com",
            role=ROLE_ADMIN,
        )
        org_b, admin_b = _create_user_with_membership(
            db,
            org_name="OrgB Uploads",
            email="orgb-uploads-admin@example.com",
            role=ROLE_ADMIN,
        )

        staff = User(
            email="orga-uploads-staff@example.com",
            full_name="orga-uploads-staff",
            hashed_password=DUMMY_HASH,
            is_active=True,
        )
        db.add(staff)
        db.flush()
        db.add(
            OrganizationMembership(
                organization_id=org_a.id,
                user_id=staff.id,
                role=ROLE_STAFF,
            )
        )
        db.commit()

        org_a_id = org_a.id
        admin_b_token = create_access_token({"sub": admin_b.id, "org_id": org_b.id})
        staff_token = create_access_token({"sub": staff.id, "org_id": org_a.id})

    denied_presign = client.post(
        "/api/v1/uploads/presign",
        json={"filename": "note.pdf", "content_type": "application/pdf"},
        headers=_auth_header(staff_token),
    )
    assert denied_presign.status_code == 403

    org_a_key = f"{org_a_id}/uploads/2026/02/test.pdf"
    denied_download = client.get(
        f"/api/v1/uploads/{org_a_key}/download",
        headers=_auth_header(admin_b_token),
    )
    assert denied_download.status_code == 404



