"""User model + repository behaviour (incl. username login identifier)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User
from app.repositories.user_repository import (
    create_user,
    get_by_email,
    get_by_id,
    get_by_login,
    normalize_email,
    normalize_username,
    update_last_login,
)


def test_create_and_read_user(session: Session) -> None:
    created = create_user(
        session,
        email="new@example.com",
        username="newbie",
        hashed_password="argon2id$fake$hash",
    )
    session.commit()

    assert isinstance(created.id, uuid.UUID)
    stored = get_by_email(session, "new@example.com")
    assert stored is not None
    assert stored.id == created.id
    assert stored.hashed_password == "argon2id$fake$hash"
    assert stored.username == "newbie"
    assert stored.is_active is True
    assert stored.last_login_at is None
    assert isinstance(stored.created_at, datetime)
    assert get_by_id(session, created.id).email == "new@example.com"  # type: ignore[union-attr]


def test_email_is_normalized(session: Session) -> None:
    created = create_user(
        session, email="  Mixed.Case@Example.COM ", username="mixed", hashed_password="hash"
    )
    session.commit()

    assert created.email == "mixed.case@example.com"
    assert get_by_email(session, "MIXED.CASE@example.com") is not None


def test_duplicate_email_is_rejected_by_the_database(session: Session) -> None:
    create_user(session, email="dupe@example.com", username="dupe1", hashed_password="hash")
    session.commit()

    with pytest.raises(IntegrityError):
        create_user(session, email="DUPE@example.com", username="dupe2", hashed_password="hash")
        session.commit()
    session.rollback()


def test_duplicate_username_is_rejected_case_insensitively(session: Session) -> None:
    create_user(session, email="a@example.com", username="Taken", hashed_password="hash")
    session.commit()

    with pytest.raises(IntegrityError):
        create_user(session, email="b@example.com", username="taken", hashed_password="hash")
        session.commit()
    session.rollback()


def test_inactive_user_is_stored_as_inactive(session: Session) -> None:
    created = create_user(
        session, email="off@example.com", username="offline", hashed_password="hash", is_active=False
    )
    session.commit()

    assert created.is_active is False


def test_get_by_login_accepts_email_or_username(session: Session) -> None:
    create_user(session, email="dave@example.com", username="dave", hashed_password="hash")
    session.commit()

    assert get_by_login(session, "dave").email == "dave@example.com"  # type: ignore[union-attr]
    assert get_by_login(session, "dave@example.com").username == "dave"  # type: ignore[union-attr]
    assert get_by_login(session, "DAVE@EXAMPLE.COM") is not None
    assert get_by_login(session, "dave ") is not None  # trimmed
    assert get_by_login(session, "nobody") is None
    assert get_by_login(session, "not an email!") is None


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


@pytest.mark.parametrize(
    "bad_username",
    ["", "ab", "x" * 33, "has space", "has-dash!", "بر"],
)
def test_normalize_username_rejects_invalid_values(bad_username: str) -> None:
    with pytest.raises(ValueError):
        normalize_username(bad_username)


def test_normalize_username_accepts_valid_values() -> None:
    assert normalize_username("  dave_99  ") == "dave_99"
    assert normalize_username("A" * 32) == "a" * 32  # canonical lowercase form


def test_create_user_requires_a_password_hash(session: Session) -> None:
    with pytest.raises(ValueError):
        create_user(session, email="x@example.com", username="xxx", hashed_password="")
