"""Verify Stripe webhook signatures without adding an SDK dependency.

Stripe signs ``f"{timestamp}.{raw_body}"`` with HMAC-SHA256 using the endpoint
signing secret. The raw body must reach this function untouched, and only
``v1`` signatures are accepted (``v0`` is a sandbox-only test scheme).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

DEFAULT_TOLERANCE_SECONDS = 300


class StripeSignatureError(ValueError):
    """Raised when a webhook payload cannot be authenticated."""


def _parse_header(header: str) -> tuple[str | None, list[str]]:
    timestamp: str | None = None
    signatures: list[str] = []
    for part in header.split(","):
        key, separator, value = part.strip().partition("=")
        if not separator:
            continue
        if key == "t" and timestamp is None:
            timestamp = value
        elif key == "v1":
            signatures.append(value)
    return timestamp, signatures


def verify_stripe_event(
    raw_body: bytes,
    signature_header: str | None,
    webhook_secret: str,
    *,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: float | None = None,
) -> dict[str, Any]:
    """Authenticate a Stripe webhook and return its parsed event body."""
    if not webhook_secret:
        raise StripeSignatureError("webhook secret is not configured")
    if not signature_header:
        raise StripeSignatureError("missing Stripe-Signature header")
    if not raw_body:
        raise StripeSignatureError("empty webhook body")

    timestamp, signatures = _parse_header(signature_header)
    if timestamp is None or not signatures:
        raise StripeSignatureError("Stripe-Signature header has no t/v1 values")

    try:
        sent_at = int(timestamp)
    except ValueError as exc:
        raise StripeSignatureError("invalid signature timestamp") from exc

    current = time.time() if now is None else now
    if tolerance_seconds <= 0 or abs(current - sent_at) > tolerance_seconds:
        raise StripeSignatureError("webhook timestamp outside tolerance")

    signed_payload = timestamp.encode("ascii") + b"." + raw_body
    expected = hmac.new(webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise StripeSignatureError("webhook signature mismatch")

    try:
        event = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StripeSignatureError("webhook body is not valid JSON") from exc
    if not isinstance(event, dict):
        raise StripeSignatureError("webhook body is not a JSON object")
    return event


def operation_key_for_session(session_id: str) -> str:
    """Bound a Stripe checkout id to an idempotent ledger key (<= 64 chars)."""
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
    return f"stripe:{digest}"
