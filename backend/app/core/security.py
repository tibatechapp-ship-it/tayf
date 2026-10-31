"""Security primitives: Argon2id password hashing + JWT access tokens.

- Passwords: argon2-cffi (Argon2id), never stored or logged in plaintext.
- Tokens: HS256 JWT with `sub` (user UUID), `iat`, `exp`, `type=access`.
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
    now = datetime.now(timezone.utc)
    ttl = expires_minutes if expires_minutes is not None else settings.JWT_EXPIRES_MINUTES
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl)).timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_effective, algorithm="HS256")


def decode_access_token(token: str) -> UUID | None:
    """Return the user UUID if the token is valid, otherwise None."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_effective,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    try:
        return UUID(str(payload["sub"]))
    except (TypeError, ValueError, AttributeError):
        return None
