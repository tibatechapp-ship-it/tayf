"""Credit top-ups: fixed packages, Stripe checkout, signed webhook fulfillment."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import pytest

from app.api.v1.endpoints import payments as payments_endpoint
from app.core.config import settings
from app.core.stripe_webhooks import operation_key_for_session
from app.services import payments

WEBHOOK_PATH = "/api/v1/webhooks/stripe"


@pytest.fixture()
def stripe_keys(monkeypatch: pytest.MonkeyPatch) -> str:
    secret = "whsec" + "_test_secret"
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk" + "_test_key")
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", secret)
    return secret


def _sign(body: bytes, secret: str, *, offset_seconds: int = 0) -> str:
    timestamp = str(int(time.time()) + offset_seconds)
    digest = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v0=ignored,v1={digest},secret=whsec_redacted,destination=we_test,payload=deadbeef"


def _event(checkout_id: str, user_id: str, *, amount: int = 500, credits: int = 50) -> bytes:
    payload: dict[str, Any] = {
        "id": "evt_test_1",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": checkout_id,
                "object": "checkout.session",
                "mode": "payment",
                "payment_status": "paid",
                "client_reference_id": user_id,
                "amount_total": amount,
                "currency": "usd",
                "metadata": {"package": "starter", "credits": str(credits)},
            }
        },
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def test_topup_packages_are_server_owned(client, stripe_keys: str) -> None:
    response = client.get("/api/v1/payments/topup/packages")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["configured"] is True
    starter = next(item for item in body["packages"] if item["name"] == "starter")
    assert starter["credits"] == 50
    assert starter["price_cents"] == 500


def test_checkout_session_requires_auth(client) -> None:
    response = client.post("/api/v1/payments/topup/checkout-session", json={"package": "starter"})
    assert response.status_code == 401


def test_checkout_session_uses_fixed_package(client, auth_headers, stripe_keys, monkeypatch) -> None:
    headers, _ = auth_headers
    captured: dict[str, Any] = {}

    async def fake_create(settings_obj, *, user_id, package):
        captured["user_id"] = user_id
        captured["package"] = package
        return payments.CheckoutSession(id="cs_test_1", url="https://checkout.stripe.com/c/pay/cs_test_1")

    monkeypatch.setattr(payments_endpoint.payments, "create_checkout_session", fake_create)
    response = client.post(
        "/api/v1/payments/topup/checkout-session",
        json={"package": "starter"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["checkout_url"].startswith("https://checkout.stripe.com/")
    assert captured["package"].credits == 50
    assert captured["package"].price_cents == 500

    unknown = client.post(
        "/api/v1/payments/topup/checkout-session",
        json={"package": "does_not_exist"},
        headers=headers,
    )
    assert unknown.status_code == 400


def test_webhook_rejects_missing_and_tampered_signatures(client, stripe_keys: str) -> None:
    body = _event("cs_test_missing", "00000000-0000-0000-0000-000000000000")
    assert client.post(WEBHOOK_PATH, content=body).status_code == 400
    tampered = client.post(
        WEBHOOK_PATH,
        content=body + b" ",
        headers={"Stripe-Signature": _sign(body, stripe_keys)},
    )
    assert tampered.status_code == 400


def test_webhook_rejects_stale_signature(client, stripe_keys: str) -> None:
    body = _event("cs_test_stale", "00000000-0000-0000-0000-000000000000")
    response = client.post(
        WEBHOOK_PATH,
        content=body,
        headers={"Stripe-Signature": _sign(body, stripe_keys, offset_seconds=-400)},
    )
    assert response.status_code == 400


def test_paid_webhook_grants_credits_once(client, auth_headers, stripe_keys: str) -> None:
    headers, data = auth_headers
    user_id = data["user"]["id"]
    body = _event("cs_test_topup_1", user_id)
    signature = _sign(body, stripe_keys)

    first = client.post(WEBHOOK_PATH, content=body, headers={"Stripe-Signature": signature})
    assert first.status_code == 200, first.text
    assert first.json() == {"received": True, "credited": True}

    duplicate = client.post(WEBHOOK_PATH, content=body, headers={"Stripe-Signature": signature})
    assert duplicate.status_code == 200

    credits_view = client.get("/api/v1/credits/me", headers=headers).json()
    assert credits_view["balance"] == 150
    topups = [entry for entry in credits_view["entries"] if entry["reason"] == "topup_stripe"]
    assert len(topups) == 1
    assert topups[0]["delta"] == 50


def test_webhook_rejects_amount_mismatch(client, auth_headers, stripe_keys: str) -> None:
    _, data = auth_headers
    body = _event("cs_test_bad_amount", data["user"]["id"], amount=1)
    response = client.post(
        WEBHOOK_PATH,
        content=body,
        headers={"Stripe-Signature": _sign(body, stripe_keys)},
    )
    assert response.status_code == 400


def test_operation_key_is_bounded() -> None:
    key = operation_key_for_session("cs_test_" + "a" * 90)
    assert key.startswith("stripe:")
    assert len(key) <= 64
