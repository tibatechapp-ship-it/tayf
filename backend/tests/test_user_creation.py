"""User model + repository behaviour."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User
from app.repositories.user_repository import (
    create_user,
    get_by_email,
    get_by_id,
    normalize_email,
    update_last_login,
)


def test_create_and_read_user(session: Session) -> None:
    created = create_user(
        session, email="new@example.com", hashed_password="argon2id$fake$hash"
    )
    session.commit()

    assert isinstance(created.id, uuid.UUID)
    stored = get_by_email(session, "new@example.com")
    assert stored is not None
    assert stored.id == created.id
    assert stored.hashed_password == "argon2id$fake$hash"
    assert stored.is_active is True
    assert stored.last_login_at is None
    assert isinstance(stored.created_at, datetime)
    assert get_by_id(session, created.id).email == "new@example.com"  # type: ignore[union-attr]


def test_email_is_normalized(session: Session) -> None:
    created = create_user(
        session, email="  Mixed.Case@Example.COM ", hashed_password="hash"
    )
    session.commit()

    assert created.email == "mixed.case@example.com"
    assert get_by_email(session, "MIXED.CASE@example.com") is not None


def test_duplicate_email_is_rejected_by_the_database(session: Session) -> None:
    create_user(session, email="dupe@example.com", hashed_password="hash")
    session.commit()

    with pytest.raises(IntegrityError):
        create_user(session, email="DUPE@example.com", hashed_password="hash")
        session.commit()
    session.rollback()


def test_inactive_user_is_stored_as_inactive(session: Session) -> None:
    created = create_user(
        session, email="off@example.com", hashed_password="hash", is_active=False
    )
    session.commit()

    assert created.is_active is False


def test_get_by_email_unknown_returns_none(session: Session) -> None:
    assert get_by_email(session, "nobody@example.com") is None


def test_update_last_login(session: Session, user: User) -> None:
    moment = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    updated = update_last_login(session, user.id, when=moment)
    session.commit()

    assert updated is not None
    assert updated.last_login_at is not None


def test_update_last_login_unknown_user_returns_none(session: Session) -> None:
    assert update_last_login(session, uuid.uuid4()) is None


@pytest.mark.parametrize(
    "bad_email",
    ["", "   ", "no-at-sign", "@example.com", "a@b", "a b@example.com", "a@example..com", "a@" + "x" * 400 + ".com"],
)
def test_normalize_email_rejects_invalid_values(bad_email: str) -> None:
    with pytest.raises(ValueError):
        normalize_email(bad_email)


def test_create_user_requires_a_password_hash(session: Session) -> None:
    with pytest.raises(ValueError):
        create_user(session, email="x@example.com", hashed_password="")
