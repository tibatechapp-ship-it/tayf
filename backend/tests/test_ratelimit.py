"""Rate limiting: sliding-window 429s on auth + job creation.

The suite runs with RATELIMIT_ENABLED=false (conftest) because other tests
hammer the auth endpoints in loops. These tests enable it per-test via
monkeypatch on the cached settings object and clear the shared window store
between scenarios — deterministic, no sleeps, no flakiness.
"""

import pytest

from app.core.config import get_settings
from app.core.ratelimit import reset_store


@pytest.fixture()
def ratelimit_enabled(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "RATELIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATELIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(settings, "RATELIMIT_AUTH_LIMIT", 3)
    monkeypatch.setattr(settings, "RATELIMIT_JOB_LIMIT", 2)
    reset_store()
    yield settings
    reset_store()


def _register(client, email, username="walker", password="Str0ngPassw0rd!"):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": username, "password": password},
    )


def test_register_blocks_after_limit(client, ratelimit_enabled):
    codes = [
        _register(client, f"rl-{i}@example.com", username=f"rl_{i}").status_code
        for i in range(5)
    ]
    assert codes[:3] == [201, 201, 201]
    assert codes[3] == 429 and codes[4] == 429


def test_rate_limit_response_has_retry_after(client, ratelimit_enabled):
    for i in range(3):
        _register(client, f"retry-{i}@example.com", username=f"retry_{i}")
    response = _register(client, "retry-3@example.com", username="retry_3")
    assert response.status_code == 429
    assert "retry-after" in {k.lower() for k in response.headers}
    assert int(response.headers["Retry-After"]) >= 1


def test_rate_limit_is_per_client_ip(client, ratelimit_enabled):
    for i in range(3):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"ip-a-{i}@example.com",
                "username": f"ip_a_{i}",
                "password": "Str0ngPassw0rd!",
            },
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        assert response.status_code == 201
    # A different client IP still gets its own window.
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "ip-b@example.com",
            "username": "ip_b_0",
            "password": "Str0ngPassw0rd!",
        },
        headers={"X-Forwarded-For": "10.0.0.2"},
    )
    assert response.status_code == 201


def test_login_rate_limited_independently_of_success(client, ratelimit_enabled):
    _register(client, "login-rl@example.com", username="login_rl")
    # fixture limit=3: register consumed one slot, two wrong logins consume the rest
    for _ in range(2):
        response = client.post(
            "/api/v1/auth/login",
            json={"username_or_email": "login-rl", "password": "wrong-password"},
        )
        assert response.status_code == 401
    response = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "login-rl", "password": "Str0ngPassw0rd!"},
    )
    # Even CORRECT credentials are refused: brute force is the threat model.
    assert response.status_code == 429


def test_job_creation_rate_limited(client, ratelimit_enabled, project_id, auth_headers):
    ratelimit_enabled.RATELIMIT_JOB_LIMIT = 2
    headers, _ = auth_headers
    codes = []
    for i in range(3):
        response = client.post(
            f"/api/v1/projects/{project_id}/jobs",
            json={"prompt": f"scene {i}", "num_scenes": 2},
            headers=headers,
        )
        codes.append(response.status_code)
    assert codes[0] == 202 and codes[1] == 202
    assert codes[2] == 429


def test_disabled_limiter_never_blocks(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "RATELIMIT_ENABLED", False)
    reset_store()
    for _ in range(6):
        response = client.post(
            "/api/v1/auth/login",
            json={"username_or_email": "nobody", "password": "nope"},
        )
        assert response.status_code == 401
