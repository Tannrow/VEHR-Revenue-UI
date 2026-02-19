from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.time import utc_now
from app.db.base import Base
from app.db.models.claim import Claim, ClaimStatus
from app.db.models.claim_event import ClaimEvent, ClaimEventType
from app.db.models.claim_ledger import ClaimLedger
from app.db.models.claim_line import ClaimLine
from app.services.claim_ledger_service import ClaimLedgerService
from app.services.claim_normalizer import ClaimNormalizer


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_claim_ledger_service_computes_totals_and_status() -> None:
    session = _session()
    claim = Claim(id=str(uuid4()), org_id="org1", external_claim_id="EXT1", created_at=utc_now(), updated_at=utc_now())
    session.add(claim)
    session.flush()

    session.add(
        ClaimLine(
            id=str(uuid4()),
            claim_id=claim.id,
            org_id=claim.org_id,
            billed_amount=Decimal("150.00"),
            expected_amount=Decimal("150.00"),
        )
    )
    session.add(
        ClaimEvent(
            id=str(uuid4()),
            claim_id=claim.id,
            org_id=claim.org_id,
            event_type=ClaimEventType.PAYMENT,
            amount=Decimal("120.00"),
            job_id="job1",
        )
    )
    session.add(
        ClaimEvent(
            id=str(uuid4()),
            claim_id=claim.id,
            org_id=claim.org_id,
            event_type=ClaimEventType.ADJUSTMENT,
            amount=Decimal("10.00"),
            job_id="job1",
        )
    )
    session.flush()

    ledger = ClaimLedgerService.compute_for_claim(session, claim.id)

    assert ledger.total_billed == Decimal("150.00")
    assert ledger.total_paid == Decimal("120.00")
    assert ledger.total_adjusted == Decimal("10.00")
    assert ledger.variance == Decimal("20.00")
    assert ledger.status == ClaimStatus.PARTIAL

    ledger_again = ClaimLedgerService.compute_for_claim(session, claim.id)
    assert ledger_again.id == ledger.id
    assert session.execute(select(ClaimLedger).where(ClaimLedger.claim_id == claim.id)).scalar_one()


def test_claim_ledger_service_flags_denial() -> None:
    session = _session()
    claim = Claim(id=str(uuid4()), org_id="org2", external_claim_id="EXT2", created_at=utc_now(), updated_at=utc_now())
    session.add(claim)
    session.flush()

    session.add(
        ClaimLine(
            id=str(uuid4()),
            claim_id=claim.id,
            org_id=claim.org_id,
            billed_amount=Decimal("50.00"),
        )
    )
    session.add(
        ClaimEvent(
            id=str(uuid4()),
            claim_id=claim.id,
            org_id=claim.org_id,
            event_type=ClaimEventType.DENIAL,
            job_id="job2",
        )
    )
    session.flush()

    ledger = ClaimLedgerService.compute_for_claim(session, claim.id)

    assert ledger.status == ClaimStatus.DENIED


def test_claim_normalizer_validates_structure() -> None:
    normalizer = ClaimNormalizer()
    payload = {
        "claim": {"org_id": "org1", "status": ClaimStatus.OPEN.value},
        "lines": [{"billed_amount": Decimal("1.00")}],
        "events": [{"event_type": ClaimEventType.PAYMENT.value}],
    }
    normalized = normalizer.normalize(payload)
    assert normalized["claim"]["org_id"] == "org1"

    with pytest.raises(ValueError):
        normalizer.normalize({})
