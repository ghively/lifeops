"""Alembic environment for Knowledge OS.

This project uses raw-SQL schema management via ``app.database.sqlite.SQLiteManager._create_tables``
for the current schema; Alembic is wired in so that *future* schema changes go through
versioned migrations instead of ad-hoc `CREATE TABLE IF NOT EXISTS` edits.

- Offline mode: renders SQL against the configured URL.
- Online mode: uses a synchronous SQLAlchemy engine against the SQLite file.

The URL defaults to the same SQLite database the app uses. Override via
``ALEMBIC_DATABASE_URL`` or the standard ``DATABASE_URL`` env var.
"""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_database_url() -> str:
    override = os.getenv("ALEMBIC_DATABASE_URL") or os.getenv("DATABASE_URL")
    if override:
        # app.config stores the URL in the form ``sqlite:///absolute/path`` — Alembic
        # accepts that directly. Normalise any ``sqlite+aiosqlite://`` to plain sqlite.
        return override.replace("sqlite+aiosqlite://", "sqlite://", 1)
    # Fall back to the same default path the app uses so `alembic upgrade head` works
    # without any env vars in local dev.
    base_dir = Path(__file__).resolve().parents[1]
    data_dir = Path(os.getenv("DATA_DIR", (base_dir / "data").as_posix()))
    return f"sqlite:///{(data_dir / 'knowledge_os.db').as_posix()}"


config.set_main_option("sqlalchemy.url", _resolve_database_url())

# No SQLAlchemy ORM models — migrations are authored as raw SQL in versions/.
target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite requires batch mode for ALTER TABLE
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
