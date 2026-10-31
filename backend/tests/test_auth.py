"""Auth acceptance tests (Argon2id + JWT)."""

from tests.conftest import register

from app.core.security import hash_password, verify_password


def test_password_hashing_roundtrip():
    hashed = hash_password("Sup3rSecret!")
    assert hashed != "Sup3rSecret!"
    assert hashed.startswith("$argon2")
    assert verify_password("Sup3rSecret!", hashed)
    assert not verify_password("wrong-password", hashed)


def test_register_returns_token_and_signup_credits(client):
    data = register(client, username="alice")
    assert data["access_token"]
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == "alice"
    assert data["balance"] == 100


def test_register_duplicate_email_conflict(client):
    register(client, username="bob", email="dup@example.com")
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "dup@example.com", "username": "bobby", "password": "Sup3rSecret!"},
    )
    assert response.status_code == 409
    assert "البريد" in response.json()["detail"]


def test_register_duplicate_username_conflict(client):
    register(client, username="carol")
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "username": "carol", "password": "Sup3rSecret!"},
    )
    assert response.status_code == 409
    assert "المستخدم" in response.json()["detail"]


def test_register_weak_password_rejected(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "username": "weakling", "password": "short"},
    )
    assert response.status_code == 422


def test_register_bad_username_rejected(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "bad@example.com", "username": "bad name!", "password": "Sup3rSecret!"},
    )
    assert response.status_code == 422


def test_login_success_by_username_and_email(client):
    register(client, username="dave", email="dave@example.com")
    for identifier in ("dave", "dave@example.com"):
        response = client.post(
            "/api/v1/auth/login",
            json={"username_or_email": identifier, "password": "Sup3rSecret!"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["access_token"]


def test_login_wrong_password_unauthorized(client):
    register(client, username="erin")
    response = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "erin", "password": "WrongPassword!"},
    )
    assert response.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_with_garbage_token(client):
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_me_returns_profile_and_balance(client, auth_headers):
    headers, data = auth_headers
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["username"] == data["user"]["username"]
    assert body["balance"] == 100
