"""SQLAlchemy engine + session factories.

Two engines share the same ``DATABASE_URL`` at runtime:

* ``async_engine`` — used by FastAPI request handlers via :func:`get_async_session`.
* ``sync_engine`` — used by Alembic in ``env.py`` for the migration run.

The ``DATABASE_URL`` env var is read via :class:`pmx_api.config.Settings`. We
accept URLs written for either driver (``postgresql://``,
``postgresql+psycopg://``, or ``postgresql+asyncpg://``) and rewrite as needed
so both engines share a single canonical connection string.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from pmx_api.config import get_settings


class DatabaseNotConfiguredError(RuntimeError):
    """Raised when we try to build an engine without ``DATABASE_URL``."""


def _require_database_url() -> str:
    settings = get_settings()
    if not settings.database_url:
        raise DatabaseNotConfiguredError(
            "DATABASE_URL is not set. Copy .env.example to .env and configure it."
        )
    return settings.database_url


def _to_sync_url(url: str) -> str:
    """Normalise ``DATABASE_URL`` to a sync driver URL (psycopg)."""
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql+asyncpg://")
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def _to_async_url(url: str) -> str:
    """Normalise ``DATABASE_URL`` to an async driver URL (psycopg async)."""
    if url.startswith("postgresql+psycopg://"):
        return url  # psycopg 3 supports async on the same driver name
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql+asyncpg://")
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


@lru_cache
def get_sync_engine() -> Engine:
    """Cached sync engine used by Alembic and any synchronous scripts."""
    return create_engine(_to_sync_url(_require_database_url()), pool_pre_ping=True)


@lru_cache
def get_async_engine() -> AsyncEngine:
    """Cached async engine used by FastAPI request handlers."""
    return create_async_engine(_to_async_url(_require_database_url()), pool_pre_ping=True)


@lru_cache
def get_sync_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_sync_engine(),
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


@lru_cache
def get_async_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_async_engine(),
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """Yield an ``AsyncSession`` and clean it up. Use as a FastAPI dependency."""
    session_factory = get_async_sessionmaker()
    async with session_factory() as session:
        yield session


def reset_engines_for_tests() -> None:
    """Drop cached engines so tests can inject a new ``DATABASE_URL``."""
    get_sync_engine.cache_clear()
    get_async_engine.cache_clear()
    get_sync_sessionmaker.cache_clear()
    get_async_sessionmaker.cache_clear()
