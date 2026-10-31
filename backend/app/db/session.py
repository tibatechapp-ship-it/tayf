"""Engine + session factory.

SQLite is the development database; the same code runs on PostgreSQL because
nothing below is engine-specific apart from the connect-time PRAGMAs (which
only fire for SQLite connections).
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def make_engine(url: str, *, echo: bool = False) -> Engine:
    kwargs: dict = {"echo": echo, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        # One file, many threads (uvicorn); SQLite needs this off-thread guard.
        kwargs["connect_args"] = {"check_same_thread": False}
    try:
        return create_engine(url, **kwargs)
    except Exception as exc:  # e.g. an unusable DATABASE_URL leaked into the env
        raise RuntimeError(
            f"Cannot create a database engine for DATABASE_URL={url!r}. "
            "Expected something like 'sqlite:///./tayf.db' or "
            "'postgresql+psycopg://user:pass@host/db'. Original error: "
            f"{exc}"
        ) from exc


@event.listens_for(Engine, "connect")
def _enable_sqlite_pragmas(dbapi_connection, _record) -> None:
    """SQLite ignores FK constraints unless asked — ON DELETE CASCADE needs this.

    WAL mode keeps concurrent reads flowing while background jobs write.
    """
    if type(dbapi_connection).__module__.split(".")[0] != "sqlite3":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


engine: Engine = make_engine(settings.DATABASE_URL, echo=settings.DB_ECHO)
SessionLocal = make_session_factory(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with SessionLocal() as session:
        yield session
