from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN
from app.core.security import create_access_token
from app.core.time import utc_now
from app.db.base import Base
from app.db.models.audit_event import AuditEvent
from app.db.models.disclosure_log import DisclosureLog
from app.db.models.form_submission import FormSubmission
from app.db.models.form_template import FormTemplate
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.patient import Patient
from app.db.models.patient_note import PatientNote
from app.db.models.service import Service
from app.db.models.service_document_template import ServiceDocumentTemplate
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


def _setup_phase2_base(session_factory):
    with session_factory() as db:
        org, admin = _create_user_with_membership(
            db,
            org_name="Phase2Org",
            email="phase2-admin@example.com",
            role=ROLE_ADMIN,
        )
        patient = Patient(
            organization_id=org.id,
            first_name="Phase",
            last_name="Two",
            dob=None,
            phone=None,
            email="phase2-patient@example.com",
        )
        db.add(patient)
        db.flush()

        service = Service(
            organization_id=org.id,
            name="SUD IOP",
            code="SUD_IOP",
            category="sud",
            is_active=True,
            sort_order=1,
        )
        db.add(service)
        db.flush()

        template = FormTemplate(
            organization_id=org.id,
            name="SUD Consent",
            description="Phase 2 required form",
            version=1,
            status="published",
            schema_json=json.dumps(
                {
                    "type": "object",
                    "fields": [
                        {"id": "ack", "label": "Acknowledge", "type": "checkbox", "required": True},
                    ],
                }
            ),
        )
        db.add(template)
        db.flush()

        db.add(
            ServiceDocumentTemplate(
                organization_id=org.id,
                service_id=service.id,
                template_id=template.id,
                requirement_type="required",
                trigger="on_enrollment",
                validity_days=365,
            )
        )
        db.commit()

        token = create_access_token({"sub": admin.id, "org_id": org.id})
        return {
            "organization_id": org.id,
            "admin_user_id": admin.id,
            "token": token,
            "patient_id": patient.id,
            "service_id": service.id,
            "template_id": template.id,
        }


def test_enrollment_auto_assigns_required_documents(tmp_path) -> None:
    database_file = tmp_path / "phase2_assignment.sqlite"
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
        seeded = _setup_phase2_base(TestingSessionLocal)
        with TestClient(app) as client:
            create_enrollment = client.post(
                f"/api/v1/patients/{seeded['patient_id']}/enrollments",
                json={
                    "service_id": seeded["service_id"],
                    "status": "active",
                    "start_date": "2026-02-08",
                },
                headers=_auth_header(seeded["token"]),
            )
            assert create_enrollment.status_code == 201
            enrollment_id = create_enrollment.json()["id"]

            patient_documents = client.get(
                f"/api/v1/patients/{seeded['patient_id']}/documents",
                headers=_auth_header(seeded["token"]),
            )
            assert patient_documents.status_code == 200
            docs = patient_documents.json()
            assert len(docs) == 1
            assert docs[0]["status"] == "required"
            assert docs[0]["enrollment_id"] == enrollment_id
            assert docs[0]["service_id"] == seeded["service_id"]
            assert docs[0]["template_id"] == seeded["template_id"]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_portal_submission_marks_document_completed_and_audits(tmp_path) -> None:
    database_file = tmp_path / "phase2_portal_submit.sqlite"
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
        seeded = _setup_phase2_base(TestingSessionLocal)
        with TestClient(app) as client:
            created = client.post(
                f"/api/v1/patients/{seeded['patient_id']}/enrollments",
                json={
                    "service_id": seeded["service_id"],
                    "status": "active",
                    "start_date": "2026-02-08",
                },
                headers=_auth_header(seeded["token"]),
            )
            assert created.status_code == 201

            docs_before_send = client.get(
                f"/api/v1/patients/{seeded['patient_id']}/documents",
                headers=_auth_header(seeded["token"]),
            )
            assert docs_before_send.status_code == 200
            document_id = docs_before_send.json()[0]["id"]

            sent = client.post(
                f"/api/v1/patients/{seeded['patient_id']}/documents/send",
                json={"service_id": seeded["service_id"]},
                headers=_auth_header(seeded["token"]),
            )
            assert sent.status_code == 200
            access_code = sent.json()["access_code"]

            portal_login = client.post(
                "/api/v1/portal/login",
                json={"patient_id": seeded["patient_id"], "code": access_code},
            )
            assert portal_login.status_code == 200
            portal_token = portal_login.json()["access_token"]
            portal_headers = _auth_header(portal_token)

            portal_documents = client.get("/api/v1/portal/documents", headers=portal_headers)
            assert portal_documents.status_code == 200
            first_doc = portal_documents.json()[0]["documents"][0]
            assert first_doc["id"] == document_id
            assert first_doc["status"] in {"required", "sent"}

            submitted = client.post(
                f"/api/v1/portal/documents/{document_id}/submit",
                json={
                    "signature_name": "Portal Patient",
                    "submitted_data": {"ack": True},
                },
                headers=portal_headers,
            )
            assert submitted.status_code == 200
            assert submitted.json()["status"] == "completed"

        with TestingSessionLocal() as db:
            submission = db.execute(
                select(FormSubmission).where(
                    FormSubmission.patient_id == seeded["patient_id"],
                    FormSubmission.form_template_id == seeded["template_id"],
                )
            ).scalar_one_or_none()
            assert submission is not None

            portal_audit = db.execute(
                select(AuditEvent).where(
                    AuditEvent.organization_id == seeded["organization_id"],
                    AuditEvent.patient_id == seeded["patient_id"],
                    AuditEvent.action == "portal.form_submitted",
                )
            ).scalar_one_or_none()
            assert portal_audit is not None
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_court_export_scopes_to_sud_legal_notes_and_logs_disclosure(tmp_path) -> None:
    database_file = tmp_path / "phase2_court_export.sqlite"
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
                org_name="CourtExportOrg",
                email="court-admin@example.com",
                role=ROLE_ADMIN,
            )
            patient = Patient(
                organization_id=org.id,
                first_name="Court",
                last_name="Patient",
                dob=None,
                phone=None,
                email="court-patient@example.com",
            )
            db.add(patient)
            db.flush()

            sud_service = Service(
                organization_id=org.id,
                name="SUD IOP",
                code="SUD_IOP",
                category="sud",
                is_active=True,
                sort_order=1,
            )
            mh_service = Service(
                organization_id=org.id,
                name="MH Counseling",
                code="MH_COUNSEL",
                category="mh",
                is_active=True,
                sort_order=2,
            )
            db.add(sud_service)
            db.add(mh_service)
            db.flush()

            included_note = PatientNote(
                organization_id=org.id,
                patient_id=patient.id,
                primary_service_id=sud_service.id,
                visibility="legal_and_clinical",
                body="SUD legal note include",
                created_by_user_id=admin.id,
                created_at=utc_now(),
            )
            excluded_sud_note = PatientNote(
                organization_id=org.id,
                patient_id=patient.id,
                primary_service_id=sud_service.id,
                visibility="clinical_only",
                body="SUD clinical-only note exclude",
                created_by_user_id=admin.id,
                created_at=utc_now(),
            )
            excluded_mh_note = PatientNote(
                organization_id=org.id,
                patient_id=patient.id,
                primary_service_id=mh_service.id,
                visibility="legal_and_clinical",
                body="MH legal note exclude",
                created_by_user_id=admin.id,
                created_at=utc_now(),
            )
            db.add_all([included_note, excluded_sud_note, excluded_mh_note])
            db.commit()

            token = create_access_token({"sub": admin.id, "org_id": org.id})
            patient_id = patient.id
            org_id = org.id
            sud_service_id = sud_service.id
            included_note_id = included_note.id

        with TestClient(app) as client:
            exported = client.post(
                f"/api/v1/patients/{patient_id}/exports/court-status",
                json={
                    "service_id": sud_service_id,
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-28",
                },
                headers=_auth_header(token),
            )
            assert exported.status_code == 200
            payload = exported.json()
            assert payload["note_count"] == 1
            assert payload["notes"][0]["id"] == included_note_id
            disclosure_log_id = payload["disclosure_log_id"]

        with TestingSessionLocal() as db:
            disclosure = db.execute(
                select(DisclosureLog).where(
                    DisclosureLog.id == disclosure_log_id,
                    DisclosureLog.organization_id == org_id,
                    DisclosureLog.patient_id == patient_id,
                    DisclosureLog.service_id == sud_service_id,
                )
            ).scalar_one_or_none()
            assert disclosure is not None
            assert disclosure.disclosed_note_count == 1

            export_audit = db.execute(
                select(AuditEvent).where(
                    AuditEvent.organization_id == org_id,
                    AuditEvent.patient_id == patient_id,
                    AuditEvent.action == "court_export.generated",
                    AuditEvent.entity_id == disclosure_log_id,
                )
            ).scalar_one_or_none()
            assert export_audit is not None
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
