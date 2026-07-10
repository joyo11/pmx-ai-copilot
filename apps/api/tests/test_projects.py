"""Tests for the M1 projects router.

Real Postgres only — SQLAlchemy 2's UUID/JSONB columns don't degrade cleanly
onto SQLite, so we skip these tests when ``TEST_DATABASE_URL`` isn't set
(the ``requires_postgres`` marker handles the skip).

We drive the app with ``httpx.AsyncClient`` over ``ASGITransport`` so the
router-side commits share the fixture's ``AsyncSession`` and roll back
cleanly at teardown.
"""

from __future__ import annotations

import uuid

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pmx_api.main import app
from tests.conftest import requires_postgres


@requires_postgres
async def test_create_list_get_roundtrip(
    override_auth_and_db: None,
    seeded_tenant: dict[str, uuid.UUID],
) -> None:
    del override_auth_and_db, seeded_tenant  # fixtures via dependency injection

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Create.
        response = await client.post(
            "/v1/projects",
            json={
                "name": "Hospital Expansion",
                "client": "Metro Health",
                "sector": "healthcare",
                "location": "Newark, NJ",
            },
        )
        assert response.status_code == 201, response.text
        created = response.json()
        assert created["name"] == "Hospital Expansion"
        assert created["status"] == "active"
        assert created["health_score"] is None
        project_id = created["id"]

        # List.
        listed = await client.get("/v1/projects")
        assert listed.status_code == 200
        ids = [row["id"] for row in listed.json()]
        assert project_id in ids

        # Get.
        detail = await client.get(f"/v1/projects/{project_id}")
        assert detail.status_code == 200
        assert detail.json()["id"] == project_id


@requires_postgres
async def test_get_project_404_when_cross_tenant(
    override_auth_and_db: None,
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    """A project owned by a different org must 404, not leak metadata."""
    del override_auth_and_db, seeded_tenant

    other_org = uuid.uuid4()
    other_project = uuid.uuid4()
    await pg_session.execute(
        text("INSERT INTO organizations (id, clerk_org_id, name) VALUES (:id, :cid, :n)"),
        {"id": other_org, "cid": "org_other", "n": "Other"},
    )
    await pg_session.execute(
        text("INSERT INTO projects (id, org_id, name) VALUES (:id, :org, :n)"),
        {"id": other_project, "org": other_org, "n": "Secret"},
    )
    await pg_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/v1/projects/{other_project}")
        assert response.status_code == 404


def test_create_requires_auth() -> None:
    """Sans auth override the endpoint 401s. Hermetic — no DB required."""
    client = TestClient(app)
    response = client.post("/v1/projects", json={"name": "X"})
    assert response.status_code == 401


def test_projects_router_registered() -> None:
    """Import-level check that main.py wires the projects router."""
    from starlette.routing import Route

    paths = {r.path for r in app.router.routes if isinstance(r, Route)}
    assert "/v1/projects" in paths
    assert "/v1/projects/{project_id}" in paths
