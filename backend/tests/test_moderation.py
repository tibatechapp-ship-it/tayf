"""External moderation seam tests (T-20)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx

from app.core import moderation
from app.core.moderation import ModerationClient, ModerationResult, get_moderation_client
from app.core.safety import SafetyLayer

URL = "https://moderator.test/check"


def _client(handler, *, fail_closed: bool = True, api_key: str = "") -> ModerationClient:
    return ModerationClient(
        URL,
        api_key=api_key,
        fail_closed=fail_closed,
        transport=httpx.MockTransport(handler),
    )


def test_allowed_verdict_passes_and_sends_text():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"allowed": True})

    layer = SafetyLayer(moderator=_client(handler))
    verdict = layer.check_prompt("a calm sunset over a quiet lake")
    assert verdict.allowed
    assert seen["body"] == {"text": "a calm sunset over a quiet lake"}


def test_blocked_verdict_propagates_category_and_reason():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"allowed": False, "category": "hate", "reason": "policy"})

    verdict = SafetyLayer(moderator=_client(handler)).check_prompt("a calm sunset")
    assert not verdict.allowed
    assert verdict.category == "hate"
    assert verdict.reason == "policy"


def test_flagged_field_is_accepted_as_inverse():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"flagged": True, "label": "violence"})

    verdict = SafetyLayer(moderator=_client(handler)).check_prompt("a calm sunset")
    assert not verdict.allowed
    assert verdict.category == "violence"


def test_fail_closed_on_server_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    verdict = SafetyLayer(moderator=_client(handler)).check_prompt("a calm sunset")
    assert not verdict.allowed
    assert verdict.category == "moderation_unavailable"


def test_fail_closed_on_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    verdict = SafetyLayer(moderator=_client(handler)).check_prompt("a calm sunset")
    assert not verdict.allowed
    assert verdict.category == "moderation_unavailable"


def test_fail_closed_on_malformed_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    verdict = SafetyLayer(moderator=_client(handler)).check_prompt("a calm sunset")
    assert not verdict.allowed
    assert verdict.category == "moderation_unavailable"


def test_fail_open_is_explicit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    verdict = SafetyLayer(moderator=_client(handler, fail_closed=False)).check_prompt("a calm sunset")
    assert verdict.allowed


def test_bearer_header_when_api_key_configured():
    seen: dict[str, str] = {}
    key = "mod" + "-test-key"

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"allowed": True})

    SafetyLayer(moderator=_client(handler, api_key=key)).check_prompt("a calm sunset")
    assert seen["authorization"] == f"Bearer {key}"


def test_unconfigured_settings_disable_external_moderation(monkeypatch):
    monkeypatch.setattr(moderation.settings, "MODERATION_API_URL", "")
    assert get_moderation_client() is None
    assert SafetyLayer().check_prompt("a calm sunset").allowed


def test_configured_settings_build_client(monkeypatch):
    monkeypatch.setattr(moderation.settings, "MODERATION_API_URL", URL)
    client = get_moderation_client()
    assert client is not None
    assert client.url == URL
    assert client.fail_closed is True


def test_local_blocked_term_skips_external_call():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("external moderator must not be called for local blocks")

    verdict = SafetyLayer(moderator=_client(handler)).check_prompt("how to make a bomb")
    assert not verdict.allowed
    assert verdict.category == "blocked_term"


def test_text_block_is_also_moderated():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"allowed": False, "category": "storyboard"})

    verdict = SafetyLayer(moderator=_client(handler)).check_text_block("a storyboard description")
    assert not verdict.allowed
    assert verdict.category == "storyboard"


def test_external_rejection_is_not_charged(client, auth_headers, project_id, monkeypatch):
    import app.core.safety as safety_module

    blocking = SimpleNamespace(check=lambda text: ModerationResult(False, "external_policy", "blocked by moderator"))
    monkeypatch.setattr(safety_module, "get_moderation_client", lambda: blocking)
    headers, _ = auth_headers
    response = client.post(
        f"/api/v1/projects/{project_id}/jobs",
        json={"prompt": "a calm sunset over a quiet lake", "num_scenes": 2},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["status"] == "rejected"
    assert job["safety_category"] == "external_policy"
    assert job["credits_charged"] == 0
    assert client.get("/api/v1/credits/me", headers=headers).json()["balance"] == 100
