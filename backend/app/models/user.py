"""User account model — Argon2id hash + optional username (login identifier).

Authentication is REAL since the unified merge (Stage 4): passwords are hashed
with Argon2id, tokens are JWTs. The shape of the data below is the contract.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )

    projects: Mapped[list["Project"]] = relationship(  # noqa: F821 - resolved by registry
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    credit_entries: Mapped[list["CreditLedger"]] = relationship(  # noqa: F821
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.id} {self.email}>"
