"""Short-lived SSE stream tickets.

Native ``EventSource`` cannot send an ``Authorization`` header, so a ticket
endpoint (Bearer-authenticated) mints a capability token that is placed in the
query string of the ``/jobs/{id}/events`` URL instead.

The ticket is an HMAC-signed, base64url-encoded JSON payload bound to one user
and one job, derived from ``JWT_SECRET``. No server state is needed; expiry and
signature make leaked tickets useless after a few minutes. Stream URLs are
never logged by this service, and the ticket cannot be used for a different job.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone
from uuid import UUID

from app.core.config import get_settings

DEFAULT_TTL_SECONDS = 300


def _secret() -> bytes:
    return get_settings().jwt_secret_effective.encode("utf-8")


def _encode(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode(body: str) -> dict | None:
    try:
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _signature(body: str) -> str:
    return hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()[:32]


def issue_stream_ticket(
    user_id: UUID | str,
    job_id: UUID | str,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> tuple[str, datetime, int]:
    """Return (ticket, expires_at, expires_in) for one user/job pair."""
    issued_at = int(time.time())
    expires_at = issued_at + ttl_seconds
    payload = {
        "sub": str(user_id),
        "jid": str(job_id),
        "iat": issued_at,
        "exp": expires_at,
        "nonce": secrets.token_hex(8),
    }
    body = _encode(payload)
    ticket = f"{body}.{_signature(body)}"
    return (
        ticket,
        datetime.fromtimestamp(expires_at, tz=timezone.utc),
        expires_at - issued_at,
    )


def verify_stream_ticket(
    ticket: str,
    *,
    user_id: UUID | str | None = None,
    job_id: UUID | str | None = None,
) -> dict | None:
    """Return the verified payload, or None when the ticket is invalid/expired."""
    if not ticket or "." not in ticket:
        return None
    body, signature = ticket.split(".", 1)
    if not hmac.compare_digest(_signature(body), signature):
        return None
    payload = _decode(body)
    if payload is None:
        return None
    try:
        expires_at = int(payload["exp"])
    except (KeyError, TypeError, ValueError):
        return None
    if expires_at < int(time.time()):
        return None
    if user_id is not None and payload.get("sub") != str(user_id):
        return None
    if job_id is not None and payload.get("jid") != str(job_id):
        return None
    return payload
