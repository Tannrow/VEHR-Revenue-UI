from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.rbac import ROLE_ADMIN
from app.core.security import create_access_token
from app.db.base import Base
from app.db.models.claim import Claim, ClaimStatus
from app.db.models.claim_event import ClaimEvent, ClaimEventType
from app.db.models.claim_ledger import ClaimLedger
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.user import User
from app.db.session import get_db
from app.main import app
from app.services.revenue_command_snapshot import record_snapshot

DUMMY_HASH = "hash-not-used"


def _setup_db(tmp_path):
  database_file = tmp_path / "revenue_command_snapshot.sqlite"
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


def _create_membership(db):
  org = Organization(name="Snapshot Org")
  db.add(org)
  db.flush()

  user = User(
    email="snapshot@example.com",
    full_name="Snapshot Tester",
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


def _seed_claims(db, org_id: str):
  claim_a = Claim(org_id=org_id, payer_name="Apex Payer", status=ClaimStatus.DENIED)
  claim_b = Claim(org_id=org_id, payer_name="Boulder Payer", status=ClaimStatus.OPEN)
  claim_c = Claim(org_id=org_id, payer_name="Apex Payer", status=ClaimStatus.OPEN)
  db.add_all([claim_a, claim_b, claim_c])
  db.flush()

  db.add(
    ClaimLedger(
      claim_id=claim_a.id,
      org_id=org_id,
      total_billed=Decimal("50000.00"),
      total_paid=Decimal("10000.00"),
      variance=Decimal("40000.00"),
      status=ClaimStatus.DENIED,
      aging_days=120,
    )
  )
  db.add(
    ClaimLedger(
      claim_id=claim_b.id,
      org_id=org_id,
      total_billed=Decimal("20000.00"),
      total_paid=Decimal("5000.00"),
      variance=Decimal("15000.00"),
      status=ClaimStatus.OPEN,
      aging_days=45,
    )
  )

  db.add(
    ClaimEvent(
      claim_id=claim_c.id,
      org_id=org_id,
      event_type=ClaimEventType.SERVICE_RECORDED,
    )
  )
  db.commit()
  return claim_a, claim_b, claim_c


def _collect_cents_values(payload):
  cents_values = []
  if isinstance(payload, dict):
    for key, value in payload.items():
      if key.endswith("_cents"):
        cents_values.append(value)
      cents_values.extend(_collect_cents_values(value))
  elif isinstance(payload, list):
    for item in payload:
      cents_values.extend(_collect_cents_values(item))
  return cents_values


def test_snapshot_deterministic_and_stored(tmp_path) -> None:
  engine, TestingSessionLocal = _setup_db(tmp_path)
  try:
    with TestingSessionLocal() as db:
      org, _ = _create_membership(db)
      _seed_claims(db, org.id)

      first = record_snapshot(db, org.id, generated_at=datetime(2026, 1, 1))
      second = record_snapshot(db, org.id, generated_at=datetime(2026, 1, 2))

      assert first.total_exposure == second.total_exposure
      assert first.expected_recovery_30_day == second.expected_recovery_30_day
      assert second.aggression_change_alerts == []
  finally:
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_snapshot_change_detection(tmp_path) -> None:
  engine, TestingSessionLocal = _setup_db(tmp_path)
  try:
    with TestingSessionLocal() as db:
      org, _ = _create_membership(db)
      claim_a, claim_b, _ = _seed_claims(db, org.id)

      baseline = record_snapshot(db, org.id, generated_at=datetime(2026, 2, 1))

      ledger_a = db.query(ClaimLedger).filter(ClaimLedger.claim_id == claim_a.id).one()
      ledger_a.total_billed = Decimal("90000.00")
      ledger_a.total_paid = Decimal("10000.00")
      ledger_a.variance = Decimal("80000.00")

      ledger_b = db.query(ClaimLedger).filter(ClaimLedger.claim_id == claim_b.id).one()
      ledger_b.aging_days = 120
      db.add_all([ledger_a, ledger_b])
      db.commit()

      updated = record_snapshot(db, org.id, generated_at=datetime(2026, 2, 2))

      assert updated.total_exposure > baseline.total_exposure
      alert_types = {alert.get("type") for alert in updated.aggression_change_alerts}
      assert "exposure_increase" in alert_types or "high_risk_claim_spike" in alert_types
  finally:
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_snapshot_endpoints_return_latest(tmp_path) -> None:
  engine, TestingSessionLocal = _setup_db(tmp_path)
  try:
    with TestingSessionLocal() as db:
      org, user = _create_membership(db)
      _seed_claims(db, org.id)
      snapshot = record_snapshot(db, org.id, generated_at=datetime(2026, 3, 1))
      token = create_access_token({"sub": user.id, "org_id": org.id})

    with TestClient(app) as client:
      response = client.get(
        "/api/v1/revenue/command/latest",
        headers={"Authorization": f"Bearer {token}"},
      )
      latest_snapshot_response = client.get(
        "/api/v1/revenue/snapshots/latest",
        headers={"Authorization": f"Bearer {token}"},
      )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == snapshot.id
    assert payload["scoring_versions"]["risk_version"]
    assert isinstance(payload["total_exposure"], str)
    assert latest_snapshot_response.status_code == 200
    latest_payload = latest_snapshot_response.json()
    assert latest_payload["snapshot_id"] == snapshot.id
    assert latest_payload["organization_id"] == org.id
    assert isinstance(latest_payload["total_exposure_cents"], int)
    assert isinstance(latest_payload["expected_recovery_30_day_cents"], int)
    assert isinstance(latest_payload["short_term_cash_opportunity_cents"], int)
    assert latest_payload["top_worklist"]
    dollars_per_hour = [item["dollars_per_hour_cents"] for item in latest_payload["top_worklist"]]
    assert dollars_per_hour == sorted(dollars_per_hour, reverse=True)
  finally:
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_snapshot_contract_enforces_cents_and_ordering(tmp_path) -> None:
  engine, TestingSessionLocal = _setup_db(tmp_path)
  try:
    with TestingSessionLocal() as db:
      org, user = _create_membership(db)
      _seed_claims(db, org.id)
      record_snapshot(db, org.id, generated_at=datetime(2026, 4, 1))
      token = create_access_token({"sub": user.id, "org_id": org.id})

    with TestClient(app) as client:
      response = client.get(
        "/api/v1/revenue/command/latest",
        headers={"Authorization": f"Bearer {token}"},
      )

    assert response.status_code == 200
    payload = response.json()
    for money_field in ("total_exposure", "expected_recovery_30_day", "short_term_cash_opportunity"):
      raw_value = payload[money_field]
      assert isinstance(raw_value, str)
      Decimal(raw_value)
    cents_values = _collect_cents_values(payload)
    assert all(isinstance(value, int) for value in cents_values), "All *_cents fields must be ints"

    top_worklist = payload.get("top_worklist") or []
    if top_worklist:
      dollars_per_hour = [item.get("dollars_per_hour_cents") for item in top_worklist]
      assert all(isinstance(value, int) for value in dollars_per_hour)
      assert dollars_per_hour == sorted(dollars_per_hour, reverse=True)

    with pytest.raises(AssertionError):
      assert all(isinstance(value, int) for value in _collect_cents_values({"bad_cents": "100"}))
    with pytest.raises(AssertionError):
      assert [100, 200] == sorted([100, 200], reverse=True)
  finally:
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
