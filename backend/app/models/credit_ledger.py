"""CreditLedger model — append-only credit accounting.

Balance of a user = SUM(delta). `balance_after` is stored on every row so an
audit never needs a replay. Negative deltas are charges; positive deltas are
grants/refunds. Rows are NEVER updated or deleted (the FK to a job uses
SET NULL so deleting a job keeps its financial history intact).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime, UUIDPrimaryKeyMixin, utc_now


class CreditLedger(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "credit_ledger"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True
    )

    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(60), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="credit_entries")  # noqa: F821
    job: Mapped["GenerationJob"] = relationship(back_populates="credit_entries")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<CreditLedger {self.user_id} {self.delta:+d} ({self.reason})>"
