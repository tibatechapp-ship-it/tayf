"""Idempotent Pro entitlements granted by paid Stripe checkout sessions."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProGrant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One Pro grant per paid checkout session.

    The unique ``stripe_session_id`` makes Stripe webhook replay harmless: a
    second delivery cannot create a second grant or flip the plan twice.
    """

    __tablename__ = "pro_grants"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stripe_session_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ProGrant {self.user_id} {self.stripe_session_id}>"
