"""Alembic environment — URL comes from app settings unless explicitly overridden.

Tests and CI override it with ``config.set_main_option("sqlalchemy.url", url)``,
so the same migration scripts run against SQLite and PostgreSQL.
"""

from __future__ import annotations

import pathlib
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make ``app`` importable no matter which directory alembic is invoked from.
BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.models import Base  # noqa: E402  (imports register every mapper)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_PLACEHOLDER = "driver://user:pass@localhost/dbname"


def _database_url() -> str:
    configured = (config.get_main_option("sqlalchemy.url") or "").strip()
    if configured and configured != _PLACEHOLDER:
        return configured
    return get_settings().database_url


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def run_migrations_offline() -> None:
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_as_batch=_is_sqlite(url),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _database_url()
    section = config.get_section(config.config_ini_section, {}) or {}
    section["sqlalchemy.url"] = url

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            # SQLite cannot ALTER most things; batch mode rewrites the table.
            render_as_batch=_is_sqlite(url),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
