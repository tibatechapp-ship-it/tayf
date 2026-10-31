"""Refresh-token flow: rotation, type separation, and abuse rejection."""

from app.db.session import SessionLocal
from app.models import User
from app.core.security import create_refresh_token


def _register(client, username: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{username}@example.com",
            "username": username,
            "password": "Sup3rSecret!",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _refresh(client, token: str):
    return client.post("/api/v1/auth/refresh", json={"refresh_token": token})


def _with_db(fn):
    """Run fn(db) against the global test database."""
    db = SessionLocal()
    try:
        return fn(db)
    finally:
        db.close()


def test_register_returns_refresh_token(client):
    data = _register(client, "refresher")
    assert data["refresh_token"]
    assert data["access_token"] != data["refresh_token"]


def test_refresh_rotates_both_tokens(client):
    data = _register(client, "rotator")
    response = _refresh(client, data["refresh_token"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["username"] == "rotator"
    assert body["balance"] == 100


def test_refreshed_access_token_works(client):
    _register(client, "worker")
    data = _register(client, "worker2")
    refreshed = _refresh(client, data["refresh_token"]).json()
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {refreshed['access_token']}"}
    )
    assert response.status_code == 200
    assert response.json()["user"]["username"] == "worker2"


def test_access_token_cannot_refresh(client):
    data = _register(client, "typeguard")
    assert _refresh(client, data["access_token"]).status_code == 401


def test_refresh_token_cannot_authorize_api(client):
    data = _register(client, "reversal")
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {data['refresh_token']}"}
    )
    assert response.status_code == 401


def test_garbage_and_tampered_refresh_rejected(client):
    data = _register(client, "tamper")
    assert _refresh(client, "not-a-jwt-at-all").status_code == 401
    tampered = data["refresh_token"][:-4] + "AAAA"
    assert _refresh(client, tampered).status_code == 401


def test_empty_refresh_body_rejected(client):
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": ""}).status_code == 422


def test_refresh_for_inactive_user_rejected(client):
    data = _register(client, "sleeper")

    def deactivate(db):
        user = db.query(User).filter(User.username == "sleeper").one()
        user.is_active = False
        db.commit()

    _with_db(deactivate)
    assert _refresh(client, data["refresh_token"]).status_code == 401


def test_refresh_of_deleted_user_rejected(client):
    data = _register(client, "ghost")

    def delete_user(db):
        db.query(User).filter(User.username == "ghost").delete()
        db.commit()

    _with_db(delete_user)
    assert _refresh(client, data["refresh_token"]).status_code == 401


def test_minted_refresh_token_roundtrip(client):
    """A directly minted refresh token (same secret) refreshes its own user."""
    data = _register(client, "target")

    def mint(db):
        user = db.query(User).filter(User.username == "target").one()
        return create_refresh_token(user.id)

    minted = _with_db(mint)
    response = _refresh(client, minted)
    assert response.status_code == 200
    assert response.json()["user"]["id"] == data["user"]["id"]


def test_login_response_carries_refresh_token(client):
    _register(client, "pairing")
    response = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "pairing", "password": "Sup3rSecret!"},
    )
    assert response.status_code == 200
    assert response.json().get("refresh_token")
