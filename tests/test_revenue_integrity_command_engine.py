from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN
from app.core.security import create_access_token
from app.db.base import Base
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.user import User
from app.db.session import get_db
from app.main import app


DUMMY_HASH = "test-hash-not-used"


def _setup_db(tmp_path):
  database_file = tmp_path / "revenue_integrity.sqlite"
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
  return engine, TestingSessionLocal


def _auth_header(token: str) -> dict[str, str]:
  return {"Authorization": f"Bearer {token}"}


def _create_membership(db):
  org = Organization(name="Revenue Integrity Org")
  db.add(org)
  db.flush()

  user = User(
    email="revenue-integrity@example.com",
    full_name="Revenue Integrity Tester",
    hashed_password=DUMMY_HASH,
    is_active=True,
  )
  db.add(user)
  db.flush()

  db.add(
    OrganizationMembership(
      organization_id=org.id,
      user_id=user.id,
      role=ROLE_ADMIN,
    )
  )
  db.commit()
  db.refresh(org)
  db.refresh(user)
  return org, user


def test_revenue_integrity_command_engine_contract(tmp_path) -> None:
  engine, TestingSessionLocal = _setup_db(tmp_path)
  try:
    with TestingSessionLocal() as db:
      org, user = _create_membership(db)
      token = create_access_token({"sub": user.id, "org_id": org.id})

    payload = {
      "claim_snapshot": {"claim_id": "CLM-12345"},
      "payer_profile": {"payer_id": "PAYER-7", "name": "Reliant Payer"},
      "org_metrics": {"revenue": 1},
      "risk_score": "0.68",
      "aging_data": {"over_90": 18000},
      "variance_metrics": {"structural": 15000, "procedural": 8000},
      "denial_codes": ["CO-45", "CO-197"],
      "adjustment_codes": ["CO-42"],
      "appeal_win_rate_history": {"rolling_win_rate": 0.62},
      "delay_history": {"avg_days": 28},
      "recovery_history": {"recent_recovery_rate": 0.45},
    }

    with TestClient(app) as client:
      response = client.post(
        "/api/v1/ai/revenue-integrity/command-engine",
        headers=_auth_header(token),
        json=payload,
      )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
      "strategic_summary",
      "revenue_exposure_analysis",
      "payer_behavior_analysis",
      "operational_priority_score_explanation",
      "expected_recovery_estimate",
      "recommended_action_sequence",
      "draft_pack",
      "escalation_thresholds",
      "data_used",
      "assumptions",
      "confidence",
    }
    assert body["revenue_exposure_analysis"]["at_risk_total"] == "23000.00"
    assert body["expected_recovery_estimate"]["recovery_probability"] == "0.50"
    assert body["expected_recovery_estimate"]["expected_recovery_value"] == "11450.17"
    assert body["escalation_thresholds"][0]["threshold"] == "50000.00"
    assert body["confidence"] == "medium"
    assert body["draft_pack"][0]["type"] == "appeal_letter"
  finally:
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
