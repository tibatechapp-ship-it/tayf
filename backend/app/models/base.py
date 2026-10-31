"""Declarative base, naming conventions and shared column mixins.

Portability rules (SQLite now, PostgreSQL later):
- primary keys are real UUIDs via ``sqlalchemy.Uuid`` (CHAR(32) on SQLite,
  native UUID on Postgres) — never auto-increment integers;
- timestamps are ``DateTime(timezone=True)`` written in UTC;
- no vendor-specific column types, no raw SQL.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, MetaData, TypeDecorator, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names: required for reliable Alembic downgrades.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utc_now() -> datetime:
    """Timezone-aware UTC timestamp (single source of 'now' for the app)."""
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """``TIMESTAMP WITH TIME ZONE`` that is ALWAYS timezone-aware in Python.

    SQLite hands back naive datetimes even for ``DateTime(timezone=True)``, so a
    row read from the DB would serialize without an offset while a freshly
    created row serializes with one — the same resource in two formats. This
    decorator normalizes on the way in and out; the DDL is unchanged, so the
    schema stays portable (and identical) on SQLite and PostgreSQL.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )
