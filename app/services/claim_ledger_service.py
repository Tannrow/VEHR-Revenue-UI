from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db.models.claim import Claim, ClaimStatus
from app.db.models.claim_event import ClaimEvent, ClaimEventType
from app.db.models.claim_line import ClaimLine
from app.db.models.claim_ledger import ClaimLedger


class ClaimLedgerService:
    @staticmethod
    def compute_for_claim(session: Session, claim_id: str) -> ClaimLedger:
        claim = session.get(Claim, claim_id)
        if claim is None:
            raise ValueError(f"Claim not found for id={claim_id}")

        claim_lines = (
            session.execute(select(ClaimLine).where(ClaimLine.claim_id == claim_id)).scalars().all()
        )
        claim_events = (
            session.execute(select(ClaimEvent).where(ClaimEvent.claim_id == claim_id)).scalars().all()
        )

        def _sum(values: list[Decimal | None]) -> Decimal:
            total = Decimal("0")
            for value in values:
                if value is not None:
                    total += Decimal(value)
            return total

        total_billed = _sum([line.billed_amount for line in claim_lines])
        total_paid = _sum([ev.amount for ev in claim_events if ev.event_type == ClaimEventType.PAYMENT])
        total_allowed = _sum([ev.amount for ev in claim_events if ev.event_type == ClaimEventType.ERA_RECEIVED])
        total_adjusted = _sum([ev.amount for ev in claim_events if ev.event_type == ClaimEventType.ADJUSTMENT])
        last_event_date = None
        for ev in claim_events:
            if ev.event_date and (last_event_date is None or ev.event_date > last_event_date):
                last_event_date = ev.event_date

        variance = total_billed - total_paid - total_adjusted

        today = utc_now()
        created_at = claim.created_at or today
        aging_days = (today - created_at).days if isinstance(today, datetime) and isinstance(created_at, datetime) else None

        status = ClaimStatus.OPEN
        if total_paid >= total_billed and total_billed > 0:
            status = ClaimStatus.PAID
        elif total_paid > 0:
            status = ClaimStatus.PARTIAL
        elif any(ev.event_type == ClaimEventType.DENIAL for ev in claim_events):
            status = ClaimStatus.DENIED

        ledger = (
            session.execute(select(ClaimLedger).where(ClaimLedger.claim_id == claim_id)).scalar_one_or_none()
        )
        if ledger is None:
            ledger = ClaimLedger(
                id=str(uuid4()),
                claim_id=claim_id,
                org_id=claim.org_id,
            )

        ledger.total_billed = total_billed
        ledger.total_paid = total_paid
        ledger.total_allowed = total_allowed
        ledger.total_adjusted = total_adjusted
        ledger.variance = variance
        ledger.status = status
        ledger.aging_days = aging_days
        ledger.last_event_date = last_event_date

        claim.status = status
        session.add(ledger)
        session.add(claim)
        session.flush()

        return ledger
