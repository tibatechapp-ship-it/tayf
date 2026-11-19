"""Branding, plan snapshots, and idempotent Pro entitlements."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from app.api.v1.endpoints import payments as payments_endpoint
from app.core import branding
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import GenerationJob, ProGrant, User
from app.services import compose

WEBHOOK_PATH = "/api/v1/webhooks/stripe"


@pytest.fixture()
def stripe_keys(monkeypatch: pytest.MonkeyPatch) -> str:
    secret = "whsec" + "_branding_secret"
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk" + "_branding_key")
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", secret)
    return secret


def _sign(body: bytes, secret: str) -> str:
    timestamp = str(int(time.time()))
    digest = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v0=ignored,v1={digest},secret=whsec_redacted,destination=we_test,payload=deadbeef"


def _event(session_id: str, user_id: str, *, package: str, credits: int, amount: int) -> bytes:
    payload: dict[str, Any] = {
        "id": "evt_branding",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "object": "checkout.session",
                "mode": "payment",
                "payment_status": "paid",
                "client_reference_id": user_id,
                "amount_total": amount,
                "currency": "usd",
                "metadata": {"package": package, "credits": str(credits)},
            }
        },
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def test_branding_helpers_fail_closed() -> None:
    assert branding.watermark_for("free") is True
    assert branding.watermark_for("pro") is False
    assert branding.watermark_for(None) is True
    assert branding.watermark_for("unexpected") is True
    assert branding.branding_snapshot("pro")["watermark"] is False
    assert branding.job_branding(None)["legacy"] is True
    assert branding.job_branding(None)["watermark"] is False
    snapshot = branding.branding_snapshot("free")
    assert branding.job_branding({"branding": snapshot})["watermark"] is True


def test_job_snapshots_server_plan(client, auth_headers, project_id) -> None:
    headers, data = auth_headers
    user_id = UUID(data["user"]["id"])
    with SessionLocal() as db:
        user = db.get(User, user_id)
        assert user is not None
        user.plan = "pro"
        db.commit()

    response = client.post(
        f"/api/v1/projects/{project_id}/jobs",
        json={"prompt": "a quiet desert at dawn", "num_scenes": 2},
        headers=headers,
    )
    assert response.status_code == 202, response.text

    with SessionLocal() as db:
        job = db.query(GenerationJob).order_by(GenerationJob.created_at.desc()).first()
        assert job is not None
        assert job.input_params["branding"] == {
            "brand": branding.BRAND_EN,
            "plan": "pro",
            "watermark": False,
            "policy_version": branding.BRANDING_POLICY_VERSION,
        }


def test_paid_pro_webhook_upgrades_plan_once(client, auth_headers, stripe_keys: str) -> None:
    headers, data = auth_headers
    user_id = data["user"]["id"]
    body = _event(
        "cs_branding_pro_1", user_id, package=branding.PRO_PACKAGE, credits=200, amount=1500
    )
    signature = _sign(body, stripe_keys)

    first = client.post(WEBHOOK_PATH, content=body, headers={"Stripe-Signature": signature})
    assert first.status_code == 200, first.text
    assert client.get("/api/v1/auth/me", headers=headers).json()["user"]["plan"] == "pro"

    duplicate = client.post(WEBHOOK_PATH, content=body, headers={"Stripe-Signature": signature})
    assert duplicate.status_code == 200
    with SessionLocal() as db:
        grants = db.query(ProGrant).filter(ProGrant.stripe_session_id == "cs_branding_pro_1").all()
        assert len(grants) == 1


def test_starter_webhook_does_not_upgrade(client, auth_headers, stripe_keys: str) -> None:
    headers, data = auth_headers
    body = _event("cs_branding_starter", data["user"]["id"], package="starter", credits=50, amount=500)
    response = client.post(WEBHOOK_PATH, content=body, headers={"Stripe-Signature": _sign(body, stripe_keys)})
    assert response.status_code == 200, response.text
    assert client.get("/api/v1/auth/me", headers=headers).json()["user"]["plan"] == "free"


def test_apply_watermark_runs_final_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(compose, "_resolve_binary", lambda name: f"/fake/{name}")
    monkeypatch.setattr(compose, "_find_font", lambda: "/fake/font.ttf")

    def fake_run(cmd: list[str]):
        Path(cmd[-1]).write_bytes(b"branded-video")
        return None

    monkeypatch.setattr(compose, "_run", fake_run)
    assert compose.apply_watermark(b"vendor-video", "webm") == b"branded-video"


def test_apply_watermark_fails_closed_without_font(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(compose, "_resolve_binary", lambda name: f"/fake/{name}")
    monkeypatch.setattr(compose, "_find_font", lambda: None)
    with pytest.raises(compose.ComposerError, match="branding font unavailable"):
        compose.apply_watermark(b"vendor-video", "mp4")


def test_payments_checkout_uses_al_manazir_product(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, *, data, auth, headers):
            captured["name"] = dict(data)[
                "line_items[0][price_data][product_data][name]"
            ]
            raise RuntimeError("stop after payload capture")

    monkeypatch.setattr(payments_endpoint.payments.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk" + "_branding_key")
    from app.core.topup import TopUpPackage

    with pytest.raises(RuntimeError, match="stop after payload capture"):
        import asyncio

        asyncio.run(
            payments_endpoint.payments.create_checkout_session(
                settings,
                user_id=UUID("00000000-0000-0000-0000-000000000001"),
                package=TopUpPackage(name="starter", credits=50, price_cents=500, currency="usd"),
            )
        )
    assert captured["name"] == "Al-Manazir credits - starter"
