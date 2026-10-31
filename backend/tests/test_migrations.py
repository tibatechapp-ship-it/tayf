"""Migration tests: the shipped scripts must build the same schema as the models,
and must roll back cleanly on both a fresh and a populated database.
"""

from __future__ import annotations

import pathlib
import sqlite3

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from app.db.session import make_engine, make_session_factory
from app.models import Base

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]


def _alembic_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_upgrade_creates_every_table(db_url: str) -> None:
    command.upgrade(_alembic_config(db_url), "head")

    db_file = db_url.replace("sqlite:///", "")
    with sqlite3.connect(db_file) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
            )
        }
        projects_ddl = connection.execute(
            "select sql from sqlite_master where name='projects'"
        ).fetchone()[0]

    assert tables == {
        "alembic_version",
        "users",
        "projects",
        "generation_jobs",
        "credit_ledger",
    }
    assert "ON DELETE CASCADE" in projects_ddl
    assert "CHECK (status IN ('draft', 'active', 'archived'))" in projects_ddl

    jobs_ddl = connection.execute(
        "select sql from sqlite_master where name='generation_jobs'"
    ).fetchone()[0]
    assert "rejected" in jobs_ddl  # extended generation_status CHECK


def test_migrations_match_the_models(db_url: str) -> None:
    """Guard against model edits that never got a migration."""
    command.upgrade(_alembic_config(db_url), "head")
    engine = make_engine(db_url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection, opts={"compare_type": True}
            )
            diff = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert diff == []


def test_downgrade_and_reupgrade_are_clean(db_url: str) -> None:
    config = _alembic_config(db_url)
    command.upgrade(config, "head")

    factory = make_session_factory(make_engine(db_url))
    with factory() as session:
        from app.repositories.project_repository import create_project
        from app.repositories.user_repository import create_user

        owner = create_user(
            session, email="mig@example.com", username="migger", hashed_password="h"
        )
        create_project(session, owner_id=owner.id, name="data that must vanish")
        session.commit()

    command.downgrade(config, "base")

    db_file = db_url.replace("sqlite:///", "")
    with sqlite3.connect(db_file) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
            )
        }
    assert tables == {"alembic_version"}

    command.upgrade(config, "head")
    with sqlite3.connect(db_file) as connection:
        empty = connection.execute("select count(*) from users").fetchone()[0]
    assert empty == 0
