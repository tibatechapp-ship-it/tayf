"""Credit accounting service — append-only ledger.

Balance = SUM(delta). Every mutation writes a ledger row with balance_after,
so the full history is auditable at any time. Rows are never mutated.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.metrics import record_credits
from app.models import CreditLedger


class InsufficientCredits(RuntimeError):
    def __init__(self, needed: int, available: int) -> None:
        super().__init__(f"need {needed} credits, balance is {available}")
        self.needed = needed
        self.available = available


def balance_of(db: Session, user_id: UUID) -> int:
    total = db.execute(
        select(func.coalesce(func.sum(CreditLedger.delta), 0)).where(
            CreditLedger.user_id == user_id
        )
    ).scalar_one()
    return int(total)


def grant(
    db: Session, user_id: UUID, amount: int, reason: str, job_id: UUID | None = None
) -> CreditLedger:
    if amount <= 0:
        raise ValueError("grant amount must be positive")
    entry = CreditLedger(
        user_id=user_id,
        job_id=job_id,
        delta=amount,
        balance_after=balance_of(db, user_id) + amount,
        reason=reason,
    )
    db.add(entry)
    db.flush()
    record_credits("granted", amount)
    return entry


def charge(
    db: Session, user_id: UUID, amount: int, reason: str, job_id: UUID | None = None
) -> CreditLedger:
    if amount <= 0:
        raise ValueError("charge amount must be positive")
    current = balance_of(db, user_id)
    if current < amount:
        raise InsufficientCredits(needed=amount, available=current)
    entry = CreditLedger(
        user_id=user_id,
        job_id=job_id,
        delta=-amount,
        balance_after=current - amount,
        reason=reason,
    )
    db.add(entry)
    db.flush()
    record_credits("charged", amount)
    return entry


def refund(
    db: Session,
    user_id: UUID,
    amount: int,
    job_id: UUID | None = None,
    reason: str = "refund_job_failed",
) -> CreditLedger:
    """Refund a failed/cancelled job (compensating entry, never negative)."""
    if amount <= 0:
        raise ValueError("refund amount must be positive")
    entry = CreditLedger(
        user_id=user_id,
        job_id=job_id,
        delta=amount,
        balance_after=balance_of(db, user_id) + amount,
        reason=reason,
    )
    db.add(entry)
    db.flush()
    record_credits("refunded", amount)
    return entry
