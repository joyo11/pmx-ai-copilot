"""Alembic environment.

Reads ``DATABASE_URL`` from :mod:`pmx_api.config` (env-driven), imports every
model so ``Base.metadata`` is populated, and runs migrations synchronously via
psycopg. Async engines stay in the FastAPI runtime.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import Base + every model module so ``Base.metadata`` includes all tables.
from pmx_api.db.models import Base
from pmx_api.db.session import _to_sync_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _database_url() -> str:
    """Prefer the CLI-provided ``-x db_url=...`` override, then env."""
    x_args = context.get_x_argument(as_dictionary=True)
    if db_url := x_args.get("db_url"):
        return _to_sync_url(db_url)

    from pmx_api.config import get_settings

    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set. Pass -x db_url=... or export DATABASE_URL.")
    return _to_sync_url(settings.database_url)


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live connection — handy for review."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database via a sync psycopg engine."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
