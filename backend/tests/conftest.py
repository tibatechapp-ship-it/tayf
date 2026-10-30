"""Test fixtures — every test gets its own isolated SQLite file.

No test ever touches the development database (``backend/tayf.db``).
"""

from __future__ import annotations

import pathlib

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db.session import make_engine, make_session_factory
from app.models import Base, User


@pytest.fixture
def db_url(tmp_path: pathlib.Path) -> str:
    return f"sqlite:///{tmp_path / 'test.db'}"


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
def user(session: Session) -> User:
    """A committed-pending user; rollback happens in the session fixture."""
    from app.repositories.user_repository import create_user

    created = create_user(
        session, email="owner@example.com", hashed_password="argon2id$fake$hash"
    )
    session.commit()
    return created


@pytest.fixture
def other_user(session: Session) -> User:
    from app.repositories.user_repository import create_user

    created = create_user(
        session, email="intruder@example.com", hashed_password="argon2id$fake$hash"
    )
    session.commit()
    return created
