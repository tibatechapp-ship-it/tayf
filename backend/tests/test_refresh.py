"""Refresh sessions: HttpOnly cookie, single-use rotation, revocation."""

from app.api.v1.endpoints.auth import REFRESH_COOKIE
from app.core.security import create_access_token, create_refresh_token, decode_access_token
from app.db.session import SessionLocal
from app.models import User
from app.services.refresh_tokens import hash_refresh_token


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


def _refresh(client):
    return client.post("/api/v1/auth/refresh")


def _set_cookie(client, value: str) -> None:
    client.cookies.clear()
    client.cookies.set(
        REFRESH_COOKIE, value, domain=client.base_url.host, path="/api/v1/auth"
    )


def _with_db(fn):
    """Run fn(db) against the global test database."""
    db = SessionLocal()
    try:
        return fn(db)
    finally:
        db.close()


def test_register_sets_httponly_strict_cookie_only(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "cookie@example.com",
            "username": "cookie",
            "password": "Sup3rSecret!",
        },
    )
    assert response.status_code == 201, response.text
    assert response.cookies.get(REFRESH_COOKIE)
    assert "refresh_token" not in response.json()
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    assert "path=/api/v1/auth" in set_cookie


def test_refresh_rotates_via_cookie_and_hides_token(client):
    _register(client, "rotator")
    old = client.cookies.get(REFRESH_COOKIE)
    response = _refresh(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["access_token"]
    assert "refresh_token" not in body
    assert body["user"]["username"] == "rotator"
    assert body["balance"] == 100
    assert client.cookies.get(REFRESH_COOKIE) != old


def test_refreshed_access_token_works(client):
    _register(client, "worker")
    data = _register(client, "worker2")
    refreshed = _refresh(client).json()
    assert data["user"]["username"] == "worker2"
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {refreshed['access_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["user"]["username"] == "worker2"


def test_access_token_cannot_refresh(client):
    data = _register(client, "typeguard")
    _set_cookie(client, data["access_token"])
    assert _refresh(client).status_code == 401


def test_refresh_token_cannot_authorize_api(client):
    _register(client, "reversal")
    raw = client.cookies.get(REFRESH_COOKIE)
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {raw}"}
    )
    assert response.status_code == 401


def test_garbage_and_tampered_cookies_rejected(client):
    _register(client, "tamper")
    assert _refresh(client).status_code == 200
    _set_cookie(client, "not-a-jwt-at-all")
    assert _refresh(client).status_code == 401
    raw = client.cookies.get(REFRESH_COOKIE)
    client.cookies.clear()
    _register(client, "tamper2")
    tampered = client.cookies.get(REFRESH_COOKIE)[:-4] + "AAAA"
    assert tampered != raw
    _set_cookie(client, tampered)
    assert _refresh(client).status_code == 401


def test_missing_cookie_rejected(client):
    assert _refresh(client).status_code == 401


def test_reuse_of_rotated_token_revokes_whole_family(client):
    _register(client, "replay")
    old = client.cookies.get(REFRESH_COOKIE)
    assert _refresh(client).status_code == 200
    current = client.cookies.get(REFRESH_COOKIE)
    assert current != old

    _set_cookie(client, old)
    assert _refresh(client).status_code == 401  # theft detected

    _set_cookie(client, current)
    assert _refresh(client).status_code == 401  # family is dead


def test_logout_revokes_session_and_clears_cookie(client):
    data = _register(client, "leaver")
    response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert response.status_code == 200, response.text
    assert client.cookies.get(REFRESH_COOKIE) is None
    assert _refresh(client).status_code == 401


def test_logout_requires_access_token(client):
    _register(client, "anonlogout")
    assert client.post("/api/v1/auth/logout").status_code == 401


def test_refresh_for_inactive_user_rejected(client):
    _register(client, "sleeper")

    def deactivate(db):
        user = db.query(User).filter(User.username == "sleeper").one()
        user.is_active = False
        db.commit()

    _with_db(deactivate)
    assert _refresh(client).status_code == 401


def test_refresh_of_deleted_user_rejected(client):
    _register(client, "ghost")

    def delete_user(db):
        db.query(User).filter(User.username == "ghost").delete()
        db.commit()

    _with_db(delete_user)
    assert _refresh(client).status_code == 401


def test_untracked_minted_token_rejected(client):
    """A valid JWT that was never issued by the server is not a session."""
    data = _register(client, "minted")

    def mint(db):
        user = db.query(User).filter(User.username == "minted").one()
        return create_refresh_token(user.id)

    raw = _with_db(mint)
    assert data["user"]["username"] == "minted"
    _set_cookie(client, raw)
    assert _refresh(client).status_code == 401


def test_login_sets_cookie_without_body_token(client):
    _register(client, "pairing")
    response = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "pairing", "password": "Sup3rSecret!"},
    )
    assert response.status_code == 200
    assert response.cookies.get(REFRESH_COOKIE)
    assert "refresh_token" not in response.json()


def test_refresh_digest_never_equals_raw_token(client):
    data = _register(client, "digest")
    assert data["access_token"]
    raw = client.cookies.get(REFRESH_COOKIE)
    assert hash_refresh_token(raw) != raw
    assert len(hash_refresh_token(raw)) == 64


def test_access_token_expiry_override_is_respected():
    from uuid import uuid4

    token = create_access_token(uuid4(), expires_minutes=1)
    payload = decode_access_token(token)
    assert payload is not None
    import jwt

    decoded = jwt.decode(token, options={"verify_signature": False})
    assert decoded["exp"] - decoded["iat"] == 60
