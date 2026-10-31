"""Shared test setup.

CRITICAL: environment variables are set BEFORE any `app` import so the cached
Settings object binds to a throwaway database/storage per test session. This
also shields the suite from stray DATABASE_URL-style variables leaked into the
hosting environment (a real problem on some CI/sandbox platforms).
"""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="tayf_test_")
os.environ["APP_ENV"] = "test"
os.environ["JWT_SECRET"] = "test-secret-not-a-real-secret-0123456789abcdef0123456789abcdef"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["DB_ECHO"] = "false"
os.environ["LOCAL_STORAGE_DIR"] = f"{_TMP}/storage"
os.environ["AI_PROVIDER"] = "mock"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["SIGNUP_CREDITS"] = "100"
os.environ["CREDIT_PER_SCENE"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import engine as global_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_database():
    """A clean database for every test (drop/create per test)."""
    Base.metadata.drop_all(bind=global_engine)
    Base.metadata.create_all(bind=global_engine)
    yield
    Base.metadata.drop_all(bind=global_engine)


@pytest.fixture()
def client():
    # The lifespan starts the TTL-cleanup loop; TestClient triggers it.
    with TestClient(app) as test_client:
        yield test_client


def register(client: TestClient, username: str = "tester", email: str | None = None) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email or f"{username}@example.com",
            "username": username,
            "password": "Sup3rSecret!",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def register_and_login(client: TestClient, username: str = "tester") -> dict:
    """Register then LOGIN so last_login_at + the login code path are exercised."""
    register(client, username=username)
    response = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": "Sup3rSecret!"},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture()
def auth_headers(client):
    data = register_and_login(client)
    return {"Authorization": f"Bearer {data['access_token']}"}, data


@pytest.fixture()
def project_id(client, auth_headers) -> str:
    headers, _ = auth_headers
    response = client.post(
        "/api/v1/projects",
        json={"name": "Test Project", "description": "for jobs"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# ---- repository-level fixtures (plain SQLAlchemy, no HTTP) ----

import pathlib  # noqa: E402

from sqlalchemy import Engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import make_engine, make_session_factory  # noqa: E402


@pytest.fixture
def db_url(tmp_path: pathlib.Path) -> str:
    return f"sqlite:///{tmp_path / 'repo_test.db'}"


@pytest.fixture
def engine(db_url: str) -> Engine:
    created = make_engine(db_url)
    Base.metadata.create_all(created)
    yield created
    created.dispose()


@pytest.fixture
def session(engine: Engine):
    factory = make_session_factory(engine)
    with factory() as db_session:
        yield db_session
        db_session.rollback()


@pytest.fixture
def user(session: Session):
    from app.core.security import hash_password
    from app.repositories.user_repository import create_user

    created = create_user(
        session,
        email="owner@example.com",
        username="owner",
        hashed_password=hash_password("Sup3rSecret!"),
    )
    session.commit()
    return created


@pytest.fixture
def other_user(session: Session):
    from app.core.security import hash_password
    from app.repositories.user_repository import create_user

    created = create_user(
        session,
        email="other@example.com",
        username="other",
        hashed_password=hash_password("Sup3rSecret!"),
    )
    session.commit()
    return created
