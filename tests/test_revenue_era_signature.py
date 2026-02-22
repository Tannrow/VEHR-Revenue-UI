from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN
from app.core.security import hash_password
from app.db.base import Base
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.revenue_era import RevenueEraClaimLine, RevenueEraFile, RevenueEraWorkItem
from app.db.models.user import User
from app.services.revenue_era import MATCH_UNMATCHED, STATUS_COMPLETE
from app.services.revenue_era_signature import compute_era_signature


def _setup_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'sig.sqlite'}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine)
    from app.db import models as _models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    return SessionLocal


def _seed_org(db) -> str:
    org = Organization(name="Signature Org")
    db.add(org)
    db.flush()
    user = User(email="sig@example.com", full_name="Sig", hashed_password=hash_password("Password123!"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganizationMembership(organization_id=org.id, user_id=user.id, role=ROLE_ADMIN))
    db.commit()
    return org.id


def test_compute_era_signature_is_stable_for_same_rows(tmp_path) -> None:
    SessionLocal = _setup_db(tmp_path)
    with SessionLocal() as db:
        org_id = _seed_org(db)
        era_file = RevenueEraFile(
            organization_id=org_id,
            file_name="sig.pdf",
            sha256="c" * 64,
            storage_ref="uploads/sig",
            status=STATUS_COMPLETE,
            current_stage="complete",
        )
        db.add(era_file)
        db.flush()

        db.add(
            RevenueEraClaimLine(
                era_file_id=era_file.id,
                line_index=1,
                claim_ref="B",
                service_date=None,
                proc_code=None,
                charge_cents=200,
                allowed_cents=150,
                paid_cents=100,
                adjustments_json=[],
                match_status=MATCH_UNMATCHED,
            )
        )
        db.add(
            RevenueEraClaimLine(
                era_file_id=era_file.id,
                line_index=0,
                claim_ref="A",
                service_date=None,
                proc_code=None,
                charge_cents=100,
                allowed_cents=90,
                paid_cents=80,
                adjustments_json=[],
                match_status=MATCH_UNMATCHED,
            )
        )
        db.add(
            RevenueEraWorkItem(
                organization_id=org_id,
                era_file_id=era_file.id,
                era_claim_line_id=None,
                type="REVIEW_REQUIRED",
                dollars_cents=20,
                payer_name="Payer",
                claim_ref="A",
                status="OPEN",
            )
        )
        db.add(
            RevenueEraWorkItem(
                organization_id=org_id,
                era_file_id=era_file.id,
                era_claim_line_id=None,
                type="UNDERPAYMENT",
                dollars_cents=100,
                payer_name="Payer",
                claim_ref="B",
                status="OPEN",
            )
        )
        db.commit()

        first = compute_era_signature(db, era_file.id)
        second = compute_era_signature(db, era_file.id)
        assert first == second
        assert first["claim_lines_count"] == 2
        assert first["work_items_count"] == 2
        assert first["totals_cents"] == 120
        assert first["claim_lines_hash"]
        assert first["work_items_hash"]
        assert first["aggregate_hash"]
