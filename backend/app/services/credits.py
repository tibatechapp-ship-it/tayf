"""Credit accounting service — atomic mutations over a materialized balance.

``users.credit_balance`` is updated with a single conditional SQL statement, so
two concurrent charges cannot both spend the same credits. Every mutation also
appends a ledger row carrying the resulting balance and an optional idempotency
key; the ledger stays append-only and remains the audit source of truth.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.metrics import record_credits
from app.models import CreditLedger, User


class InsufficientCredits(RuntimeError):
    def __init__(self, needed: int, available: int) -> None:
        super().__init__(f"need {needed} credits, balance is {available}")
        self.needed = needed
        self.available = available


class UserNotFound(RuntimeError):
    def __init__(self, user_id: UUID) -> None:
        super().__init__(f"user {user_id} does not exist")


def balance_of(db: Session, user_id: UUID) -> int:
    balance = db.execute(
        select(User.credit_balance).where(User.id == user_id)
    ).scalar_one_or_none()
    return int(balance or 0)


def _lock_user(db: Session, user_id: UUID) -> None:
    """Lock the owning row on PostgreSQL.

    SQLite ignores FOR UPDATE and a prior SELECT would create a read snapshot
    that blocks a later write (SQLITE_BUSY_SNAPSHOT), so the atomic UPDATE
    below is the whole concurrency strategy there.
    """
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        return
    user = db.execute(
        select(User).where(User.id == user_id).with_for_update()
    ).scalar_one_or_none()
    if user is None:
        raise UserNotFound(user_id)


def _existing_operation(
    db: Session, user_id: UUID, operation_key: str
) -> CreditLedger | None:
    return db.execute(
        select(CreditLedger).where(
            CreditLedger.user_id == user_id,
            CreditLedger.operation_key == operation_key,
        )
    ).scalars().first()


def _mutate(
    db: Session,
    user_id: UUID,
    amount: int,
    reason: str,
    job_id: UUID | None,
    operation_key: str | None,
    *,
    charge: bool,
    metric: str,
) -> CreditLedger:
    if amount <= 0:
        raise ValueError("credit amount must be positive")
    if operation_key is not None and not operation_key.strip():
        raise ValueError("operation_key must not be blank")
    if operation_key is not None and len(operation_key) > 64:
        raise ValueError("operation_key must be at most 64 characters")

    _lock_user(db, user_id)

    try:
        # A savepoint lets a duplicate idempotency key undo its tentative
        # balance change without rolling back the caller's other work.
        with db.begin_nested():
            if charge:
                result = db.execute(
                    update(User)
                    .where(User.id == user_id, User.credit_balance >= amount)
                    .values(credit_balance=User.credit_balance - amount)
                )
                if result.rowcount != 1:
                    raise InsufficientCredits(
                        needed=amount, available=balance_of(db, user_id)
                    )
                delta = -amount
            else:
                result = db.execute(
                    update(User)
                    .where(User.id == user_id)
                    .values(credit_balance=User.credit_balance + amount)
                )
                if result.rowcount != 1:
                    raise UserNotFound(user_id)
                delta = amount

            balance_after = balance_of(db, user_id)
            entry = CreditLedger(
                user_id=user_id,
                job_id=job_id,
                delta=delta,
                balance_after=balance_after,
                reason=reason,
                operation_key=operation_key,
            )
            db.add(entry)
            db.flush()
    except IntegrityError:
        if operation_key is not None:
            existing = _existing_operation(db, user_id, operation_key)
            if existing is not None:
                return existing
        raise

    record_credits(metric, amount)
    return entry


def grant(
    db: Session,
    user_id: UUID,
    amount: int,
    reason: str,
    job_id: UUID | None = None,
    operation_key: str | None = None,
) -> CreditLedger:
    return _mutate(
        db,
        user_id,
        amount,
        reason,
        job_id,
        operation_key,
        charge=False,
        metric="granted",
    )


def charge(
    db: Session,
    user_id: UUID,
    amount: int,
    reason: str,
    job_id: UUID | None = None,
    operation_key: str | None = None,
) -> CreditLedger:
    return _mutate(
        db,
        user_id,
        amount,
        reason,
        job_id,
        operation_key,
        charge=True,
        metric="charged",
    )


def refund(
    db: Session,
    user_id: UUID,
    amount: int,
    job_id: UUID | None = None,
    reason: str = "refund_job_failed",
    operation_key: str | None = None,
) -> CreditLedger:
    """Refund a failed/cancelled job (compensating entry, never negative)."""
    return _mutate(
        db,
        user_id,
        amount,
        reason,
        job_id,
        operation_key,
        charge=False,
        metric="refunded",
    )
