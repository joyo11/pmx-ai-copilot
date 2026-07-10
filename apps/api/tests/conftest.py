"""Shared pytest fixtures for the M1 API test suite.

Design notes:

* We don't try to shoehorn pgvector or JSONB into SQLite. If a real Postgres
  URL is available on ``TEST_DATABASE_URL``, DB-touching tests run against
  it; otherwise those tests are marked ``skip`` with a clear reason so CI
  fails loudly if the URL was expected.
* The Clerk auth dependency is overridden with a static ``CurrentUser`` so
  routers can be exercised without a signed JWT round-trip. Each test that
  hits a router installs / removes the override in its own fixture scope.
* Any test that needs the internal user/org mirror bootstraps those rows
  itself against the real Postgres.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from pmx_api.db.session import _to_async_url
from pmx_api.deps import CurrentUser, get_current_user

# --------------------------------------------------------------------------- #
# Test-only Postgres detection                                                #
# --------------------------------------------------------------------------- #

TEST_DATABASE_URL_ENV = "TEST_DATABASE_URL"


def _postgres_url() -> str | None:
    """Return an async-driver Postgres URL if the test DB is available."""
    raw = os.environ.get(TEST_DATABASE_URL_ENV)
    if not raw:
        return None
    return _to_async_url(raw)


requires_postgres = pytest.mark.skipif(
    _postgres_url() is None,
    reason=(
        "Requires TEST_DATABASE_URL pointing at a Postgres 15+ instance with "
        "pgvector installed. Set it in CI or a local Neon branch."
    ),
)


# --------------------------------------------------------------------------- #
# Async DB engine + session per test                                          #
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def pg_session() -> AsyncIterator[AsyncSession]:
    """Yield an ``AsyncSession`` bound to the test Postgres URL.

    We open an outer transaction and a nested SAVEPOINT so router-side
    ``commit()`` calls become releases against the savepoint (not the outer
    transaction). At teardown we roll back the outer transaction, wiping
    every row the test inserted.

    Pattern: https://docs.sqlalchemy.org/en/20/orm/session_transaction.html
    """
    from sqlalchemy import event

    url = _postgres_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL not set")
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            outer_txn = await connection.begin()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            # Start a savepoint. After every commit the router issues, we
            # start a fresh savepoint so subsequent writes stay under the
            # outer rollback umbrella.
            await session.begin_nested()

            sync_session = session.sync_session

            @event.listens_for(sync_session, "after_transaction_end")
            def _restart_savepoint(session_: Any, transaction: Any) -> None:
                # When the savepoint ends (commit or rollback from the router),
                # start a fresh one so the next write still sits inside the
                # outer transaction we roll back at teardown.
                if transaction.nested and not transaction.parent.nested:
                    session_.begin_nested()

            try:
                yield session
            finally:
                event.remove(sync_session, "after_transaction_end", _restart_savepoint)
                await session.close()
                if outer_txn.is_active:
                    await outer_txn.rollback()
    finally:
        await engine.dispose()


# --------------------------------------------------------------------------- #
# Fake CurrentUser + tenant fixture                                           #
# --------------------------------------------------------------------------- #


@pytest.fixture
def fake_clerk_user() -> CurrentUser:
    """A CurrentUser stand-in for router tests that bypass Clerk verification."""
    return CurrentUser(
        user_id="user_test_m1",
        org_id="org_test_m1",
        role="project_manager",
        email="pm@test.local",
    )


@pytest_asyncio.fixture
async def seeded_tenant(
    pg_session: AsyncSession, fake_clerk_user: CurrentUser
) -> dict[str, uuid.UUID]:
    """Insert an organization + user row so ``resolve_tenant`` succeeds.

    Returns ``{"org_uuid": ..., "user_uuid": ...}`` for callers to use as FKs
    when seeding downstream fixtures (projects, documents, sessions).
    """
    org_uuid = uuid.uuid4()
    user_uuid = uuid.uuid4()
    assert fake_clerk_user.org_id is not None  # narrowed for mypy
    await pg_session.execute(
        text(
            """
            INSERT INTO organizations (id, clerk_org_id, name)
            VALUES (:id, :clerk_org_id, :name)
            """
        ),
        {"id": org_uuid, "clerk_org_id": fake_clerk_user.org_id, "name": "Test Org"},
    )
    await pg_session.execute(
        text(
            """
            INSERT INTO users (id, clerk_user_id, org_id, email, role)
            VALUES (:id, :clerk_user_id, :org_id, :email, :role)
            """
        ),
        {
            "id": user_uuid,
            "clerk_user_id": fake_clerk_user.user_id,
            "org_id": org_uuid,
            "email": fake_clerk_user.email,
            "role": "project_manager",
        },
    )
    await pg_session.commit()
    return {"org_uuid": org_uuid, "user_uuid": user_uuid}


# --------------------------------------------------------------------------- #
# FastAPI dependency overrides                                                #
# --------------------------------------------------------------------------- #


@pytest.fixture
def override_auth(fake_clerk_user: CurrentUser) -> Iterator[None]:
    """Swap ``get_current_user`` for a fixture-backed stub.

    Yields to the test, then restores the original overrides so parallel or
    later tests aren't affected.
    """
    from pmx_api.main import app

    original: dict[Any, Any] = dict(app.dependency_overrides)
    app.dependency_overrides[get_current_user] = lambda: fake_clerk_user
    try:
        yield
    finally:
        app.dependency_overrides = original


@pytest.fixture
def override_auth_and_db(fake_clerk_user: CurrentUser, pg_session: AsyncSession) -> Iterator[None]:
    """Bind both the Clerk auth stub and a shared Postgres session to the app.

    Every DB dep resolves to the same ``pg_session`` so router-side commits
    stay inside the outer SAVEPOINT and roll back cleanly at teardown.
    """
    from pmx_api.deps import get_db
    from pmx_api.main import app

    original: dict[Any, Any] = dict(app.dependency_overrides)

    async def _shared_db() -> AsyncIterator[AsyncSession]:
        yield pg_session

    app.dependency_overrides[get_current_user] = lambda: fake_clerk_user
    app.dependency_overrides[get_db] = _shared_db
    try:
        yield
    finally:
        app.dependency_overrides = original


__all__ = ["TEST_DATABASE_URL_ENV", "requires_postgres"]
