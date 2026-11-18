"""Refresh token issuance, atomic rotation and revocation.

Security model
--------------
- The refresh JWT is delivered ONLY as an HttpOnly cookie (never in a JSON
  body), so page JavaScript cannot read it.
- The database stores only SHA-256(token) with a unique constraint; a stolen
  database row is not a usable token.
- Rotation is one conditional UPDATE: exactly one caller can consume a token.
  Presenting an already-consumed token is treated as theft and revokes the
  whole active family for that user.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_refresh_token
from app.models import RefreshToken, User


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue(db: Session, user: User) -> str:
    """Create a tracked refresh token and return the raw JWT for the cookie."""
    raw = create_refresh_token(user.id)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.JWT_REFRESH_EXPIRES_DAYS),
        )
    )
    db.commit()  # the session dependency does not auto-commit on response
    return raw


def _revoke_all_active(db: Session, user_id) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    db.commit()


def consume(db: Session, raw: str, user_id) -> bool:
    """Atomically consume a refresh token. False = invalid or replayed.

    A replay means the token was already used (or revoked on logout): revoke
    every still-active token for the user, because a copy is in the wild.
    """
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == hash_refresh_token(raw),
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        .values(revoked_at=now)
    )
    if result.rowcount == 1:
        db.commit()
        return True

    db.rollback()
    known = db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(raw),
            RefreshToken.user_id == user_id,
        )
    )
    if known is not None:
        _revoke_all_active(db, user_id)
    return False


def revoke(db: Session, raw: str, user_id) -> bool:
    """Revoke one token on logout. Returns whether a live token was found."""
    result = db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == hash_refresh_token(raw),
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )
    db.commit()
    return result.rowcount == 1
