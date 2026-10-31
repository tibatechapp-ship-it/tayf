"""User persistence. No HTTP, no password hashing here — the API layer owns that."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, utc_now

EMAIL_MAX_LENGTH = 320
USERNAME_MAX_LENGTH = 32
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


def normalize_email(email: str) -> str:
    """Trim + lowercase so 'A@B.com ' and 'a@b.com' cannot become two accounts."""
    normalized = email.strip().lower()
    if not normalized or len(normalized) > EMAIL_MAX_LENGTH or " " in normalized:
        raise ValueError("invalid email address")

    local, _, domain = normalized.partition("@")
    if not local or not domain or "@" in domain or "." not in domain:
        raise ValueError("invalid email address")
    if domain.startswith(".") or domain.endswith(".") or ".." in domain:
        raise ValueError("invalid email address")
    return normalized


def normalize_username(username: str) -> str:
    """3-32 chars of [a-zA-Z0-9_], trimmed and LOWERCASED — uniqueness must be
    case-insensitive, and storing one canonical form is the honest way to get
    that on both SQLite and PostgreSQL."""
    cleaned = (username or "").strip().lower()
    if not _USERNAME_RE.fullmatch(cleaned):
        raise ValueError("username must be 3-32 characters of letters, digits or _")
    return cleaned


def create_user(
    session: Session,
    *,
    email: str,
    username: str,
    hashed_password: str,
    is_active: bool = True,
) -> User:
    """Insert a user. Raises ``ValueError`` on bad input, ``IntegrityError`` on duplicates."""
    if not hashed_password:
        raise ValueError("hashed_password must not be empty")

    user = User(
        email=normalize_email(email),
        username=normalize_username(username),
        hashed_password=hashed_password,
        is_active=is_active,
    )
    session.add(user)
    session.flush()  # surfaces IntegrityError here, inside the caller's transaction
    return user


def get_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == normalize_email(email)))


def get_by_username(session: Session, username: str) -> User | None:
    cleaned = normalize_username(username)
    return session.scalar(select(User).where(User.username == cleaned))


def get_by_login(session: Session, identifier: str) -> User | None:
    """Email OR username — whatever the user typed into the login box."""
    ident = (identifier or "").strip()
    if "@" in ident:
        return get_by_email(session, ident)
    try:
        cleaned = normalize_username(ident)
    except ValueError:
        return None
    return session.scalar(select(User).where(User.username == cleaned))


def get_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)


def update_last_login(
    session: Session, user_id: uuid.UUID, *, when: datetime | None = None
) -> User | None:
    """Record a successful login. Returns ``None`` when the user does not exist."""
    user = session.get(User, user_id)
    if user is None:
        return None
    user.last_login_at = when or utc_now()
    session.flush()
    return user
