from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN
from app.core.security import hash_password
from app.db.base import Base
from app.db.invariants.revenue_era_invariants import run_revenue_era_invariants
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.revenue_era import RevenueEraClaimLine, RevenueEraFile, RevenueEraStructuredResult, RevenueEraWorkItem
from app.db.models.user import User
from app.services.revenue_era import MATCH_UNMATCHED, STATUS_COMPLETE, STATUS_ERROR


def _setup_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'inv.sqlite'}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine)
    from app.db import models as _models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    return SessionLocal


def _seed_org(db) -> str:
    org = Organization(name="Invariant Org")
    db.add(org)
    db.flush()
    user = User(email="inv@example.com", full_name="Inv", hashed_password=hash_password("Password123!"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganizationMembership(organization_id=org.id, user_id=user.id, role=ROLE_ADMIN))
    db.commit()
    return org.id


def test_invariants_pass_for_complete_file(tmp_path) -> None:
    SessionLocal = _setup_db(tmp_path)
    with SessionLocal() as db:
        org_id = _seed_org(db)
        era_file = RevenueEraFile(
            organization_id=org_id,
            file_name="ok.pdf",
            sha256="a" * 64,
            storage_ref="uploads/x",
            status=STATUS_COMPLETE,
            current_stage="complete",
        )
        db.add(era_file)
        db.flush()
        db.add(
            RevenueEraStructuredResult(
                era_file_id=era_file.id,
                llm="azure_openai",
                deployment="dep",
                api_version="v1",
                prompt_version="p1",
                structured_json={"claim_lines": [{"claim_ref": "1"}]},
            )
        )
        db.add(
            RevenueEraClaimLine(
                era_file_id=era_file.id,
                line_index=0,
                claim_ref="CLM1",
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
                claim_ref="CLM1",
                status="OPEN",
            )
        )
        era_file.stage_completed_at = era_file.created_at
        db.add(era_file)
        db.commit()
        result = run_revenue_era_invariants(db, organization_id=org_id)
        assert result["pass"] is True
        assert result["failures"] == []


def test_invariants_fail_for_error_with_partial_rows(tmp_path) -> None:
    SessionLocal = _setup_db(tmp_path)
    with SessionLocal() as db:
        org_id = _seed_org(db)
        era_file = RevenueEraFile(
            organization_id=org_id,
            file_name="bad.pdf",
            sha256="b" * 64,
            storage_ref="uploads/y",
            status=STATUS_ERROR,
            current_stage="structuring",
        )
        db.add(era_file)
        db.flush()
        db.add(
            RevenueEraClaimLine(
                era_file_id=era_file.id,
                line_index=0,
                claim_ref="CLM2",
                service_date=None,
                proc_code=None,
                charge_cents=100,
                allowed_cents=90,
                paid_cents=80,
                adjustments_json=[],
                match_status=MATCH_UNMATCHED,
            )
        )
        db.commit()
        result = run_revenue_era_invariants(db, organization_id=org_id)
        assert result["pass"] is False
        names = {failure["name"] for failure in result["failures"]}
        assert "failed_state_partial_rows" in names
