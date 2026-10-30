"""Engine + session factory.

SQLite is the development database; the same code runs on PostgreSQL because
nothing below is engine-specific apart from the connect-time PRAGMA (which only
fires for SQLite connections).
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def make_engine(url: str, *, echo: bool = False) -> Engine:
    kwargs: dict = {"echo": echo, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        # One file, many threads (uvicorn); SQLite needs this off-thread guard.
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:
    """SQLite ignores FK constraints unless asked — ON DELETE CASCADE needs this."""
    if type(dbapi_connection).__module__.split(".")[0] != "sqlite3":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


_settings = get_settings()
engine: Engine = make_engine(_settings.database_url, echo=_settings.db_echo)
SessionLocal = make_session_factory(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency for Stage 4 (one session per request)."""
    with SessionLocal() as session:
        yield session
