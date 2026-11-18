"""Stripe REST client for credit top-ups (no third-party SDK dependency).

The server owns package prices and passes them as ad-hoc ``price_data`` to
Stripe; clients can only choose a package name. Credits are granted later by
the signed webhook, never by the checkout redirect.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings
from app.core.topup import TopUpPackage

STRIPE_API_URL = "https://api.stripe.com/v1/checkout/sessions"
CHECKOUT_HOST = "https://checkout.stripe.com/"
REQUEST_TIMEOUT_SECONDS = 20.0


class StripeError(RuntimeError):
    """Raised when Stripe cannot create a checkout session."""


@dataclass(frozen=True)
class CheckoutSession:
    id: str
    url: str


async def create_checkout_session(
    settings: Settings,
    *,
    user_id: uuid.UUID,
    package: TopUpPackage,
) -> CheckoutSession:
    """Create one Stripe Checkout Session for a fixed credit package."""
    success_url = settings.TOPUP_SUCCESS_URL
    separator = "&" if "?" in success_url else "?"
    success_url = f"{success_url}{separator}session_id={{CHECKOUT_SESSION_ID}}"

    form: list[tuple[str, str]] = [
        ("mode", "payment"),
        ("customer_email", ""),
        ("client_reference_id", str(user_id)),
        ("success_url", success_url),
        ("cancel_url", settings.TOPUP_CANCEL_URL),
        ("line_items[0][quantity]", "1"),
        ("line_items[0][price_data][currency]", package.currency),
        ("line_items[0][price_data][unit_amount]", str(package.price_cents)),
        ("line_items[0][price_data][product_data][name]", f"Tayf credits - {package.name}"),
        ("metadata[package]", package.name),
        ("metadata[credits]", str(package.credits)),
    ]
    # Do not ask Stripe to create an empty Customer record for guest checkout.
    form = [item for item in form if item[1] != ""]

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                STRIPE_API_URL,
                data=form,
                auth=(settings.STRIPE_SECRET_KEY, ""),
                headers={
                    "Idempotency-Key": f"tayf_topup_{uuid.uuid4().hex}",
                    "User-Agent": "tayf-studio/1.0",
                },
            )
            response.raise_for_status()
            body: dict[str, Any] = response.json()
    except httpx.HTTPError as exc:
        raise StripeError("Stripe checkout is temporarily unavailable") from exc
    except ValueError as exc:
        raise StripeError("Stripe returned an invalid response") from exc

    session_id = body.get("id")
    checkout_url = body.get("url")
    if not isinstance(session_id, str) or not session_id:
        raise StripeError("Stripe did not return a session id")
    if not isinstance(checkout_url, str) or not checkout_url.startswith(CHECKOUT_HOST):
        raise StripeError("Stripe returned an invalid checkout URL")
    return CheckoutSession(id=session_id, url=checkout_url)
