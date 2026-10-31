"""Security primitives: Argon2id password hashing + JWT access/refresh tokens.

- Passwords: argon2-cffi (Argon2id), never stored or logged in plaintext.
- Access tokens: HS256 JWT with `sub` (user UUID), `iat`, `exp`, `type=access`.
- Refresh tokens: HS256 JWT with `type=refresh` and a longer lifetime; each
  refresh call rotates the pair (old refresh stays valid until expiry —
  stateless rotation; server-side revocation lists are future work).
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings

_password_hasher = PasswordHasher()  # defaults: Argon2id, strong parameters


def hash_password(plain: str) -> str:
    return _password_hasher.hash(plain)


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: UUID, expires_minutes: int | None = None) -> str:
    return _encode_token(user_id, settings.JWT_EXPIRES_MINUTES, "access")


def create_refresh_token(user_id: UUID) -> str:
    return _encode_token(user_id, settings.JWT_REFRESH_EXPIRES_DAYS * 24 * 60, "refresh")


def _encode_token(user_id: UUID, ttl_minutes: int, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
        "type": token_type,
    }
    return jwt.encode(payload, settings.jwt_secret_effective, algorithm="HS256")


def decode_token(token: str, expected_type: str = "access") -> UUID | None:
    """Return the user UUID if the token is valid and of the expected type."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_effective,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    try:
        return UUID(str(payload["sub"]))
    except (TypeError, ValueError, AttributeError):
        return None


def decode_access_token(token: str) -> UUID | None:
    """Return the user UUID if the access token is valid, otherwise None."""
    return decode_token(token, expected_type="access")


def decode_refresh_token(token: str) -> UUID | None:
    """Return the user UUID if the refresh token is valid, otherwise None."""
    return decode_token(token, expected_type="refresh")
