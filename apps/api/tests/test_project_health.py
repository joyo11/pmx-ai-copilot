"""Tests for the M2 project-health service + endpoints.

Kept in a separate module from ``test_health.py`` (which covers the
``/v1/health`` liveness probe) so the two concerns stay searchable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pmx_api.main import app
from pmx_api.services import health as health_service
from tests.conftest import requires_postgres


async def _seed_project(pg_session: AsyncSession, seeded_tenant: dict[str, uuid.UUID]) -> uuid.UUID:
    project_id = uuid.uuid4()
    await pg_session.execute(
        text("INSERT INTO projects (id, org_id, name) VALUES (:id, :org, :n)"),
        {"id": project_id, "org": seeded_tenant["org_uuid"], "n": "Health Test"},
    )
    await pg_session.commit()
    return project_id


# --------------------------------------------------------------------------- #
# Factor calculators                                                          #
# --------------------------------------------------------------------------- #


@requires_postgres
async def test_compute_health_neutral_for_empty_project(
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    """A fresh project with no data should score 100 (nothing wrong yet)."""
    project_id = await _seed_project(pg_session, seeded_tenant)
    result = await health_service.compute_project_health(pg_session, project_id)
    assert result.score == 100
    # Every factor should carry the "neutral" flag detail.
    for factor in result.factors:
        assert factor.sub_score == 1.0


@requires_postgres
async def test_compute_health_penalises_budget_overrun(
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    """25% overrun should knock the budget factor sub-score to 0."""
    project_id = await _seed_project(pg_session, seeded_tenant)
    await pg_session.execute(
        text(
            "INSERT INTO budget_lines (project_id, actual_cents, forecast_cents) "
            "VALUES (:pid, :a, :f)"
        ),
        {"pid": project_id, "a": 125_000_00, "f": 100_000_00},
    )
    await pg_session.commit()

    result = await health_service.compute_project_health(pg_session, project_id)
    budget = next(f for f in result.factors if f.key == "budget_variance")
    assert budget.sub_score == 0.0
    # Score should drop by ~25 from the 100 baseline.
    assert result.score <= 75


@requires_postgres
async def test_compute_health_penalises_worst_slip_task(
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    """A single 30d-slipping task should zero the schedule factor."""
    project_id = await _seed_project(pg_session, seeded_tenant)
    await pg_session.execute(
        text(
            "INSERT INTO schedule_tasks (project_id, name, slip_days) "
            "VALUES (:pid, 'Slab pour', 30)"
        ),
        {"pid": project_id},
    )
    await pg_session.commit()

    result = await health_service.compute_project_health(pg_session, project_id)
    sched = next(f for f in result.factors if f.key == "schedule_variance")
    assert sched.sub_score == 0.0


@requires_postgres
async def test_compute_health_penalises_open_risks(
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    """Open risks weighted by severity should reduce the open_risks factor."""
    project_id = await _seed_project(pg_session, seeded_tenant)
    now = datetime.now(UTC)
    # Two open severity-5 risks = 10, well under the cap (15). Sub-score
    # should be 1 - (10/15) = 0.333...
    await pg_session.execute(
        text(
            """
            INSERT INTO risks (
              project_id, category, title, description, severity, likelihood,
              business_impact, recommended_action, confidence, status, detected_at
            ) VALUES
              (:pid, 'schedule', 't1', 'd', 5, 0.9, 'bi', 'ra', 0.9, 'open', :now),
              (:pid, 'budget', 't2', 'd', 5, 0.9, 'bi', 'ra', 0.9, 'open', :now)
            """
        ),
        {"pid": project_id, "now": now},
    )
    await pg_session.commit()

    result = await health_service.compute_project_health(pg_session, project_id)
    risks_factor = next(f for f in result.factors if f.key == "open_risk_count")
    assert 0.3 < risks_factor.sub_score < 0.4
    assert result.score < 100


@requires_postgres
async def test_compute_health_penalises_overdue_rfis(
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    project_id = await _seed_project(pg_session, seeded_tenant)
    old = date.today() - timedelta(days=21)
    await pg_session.execute(
        text(
            "INSERT INTO rfis (project_id, number, status, submitted_date) "
            "VALUES (:pid, :n, 'open', :d)"
        ),
        [{"pid": project_id, "n": f"R-{i}", "d": old} for i in range(5)],
    )
    await pg_session.commit()

    result = await health_service.compute_project_health(pg_session, project_id)
    rfi = next(f for f in result.factors if f.key == "overdue_rfi_count")
    assert rfi.sub_score == 0.0


@requires_postgres
async def test_compute_health_penalises_doc_failures(
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    project_id = await _seed_project(pg_session, seeded_tenant)
    user_uuid = seeded_tenant["user_uuid"]
    # One ready, one failed → 50% healthy.
    await pg_session.execute(
        text(
            "INSERT INTO documents (project_id, uploaded_by, kind, filename, storage_uri, status) "
            "VALUES (:pid, :u, 'pdf_generic', :fn, :uri, :st)"
        ),
        [
            {
                "pid": project_id,
                "u": user_uuid,
                "fn": "ok.pdf",
                "uri": "file:///tmp/ok.pdf",
                "st": "ready",
            },
            {
                "pid": project_id,
                "u": user_uuid,
                "fn": "bad.pdf",
                "uri": "file:///tmp/bad.pdf",
                "st": "failed",
            },
        ],
    )
    await pg_session.commit()

    result = await health_service.compute_project_health(pg_session, project_id)
    doc = next(f for f in result.factors if f.key == "document_ingestion_health")
    assert doc.sub_score == 0.5


# --------------------------------------------------------------------------- #
# Snapshot persistence                                                        #
# --------------------------------------------------------------------------- #


@requires_postgres
async def test_snapshot_project_health_inserts_row_and_mirrors_score(
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    """snapshot_project_health writes a snapshot AND mirrors ``projects.health_score``."""
    project_id = await _seed_project(pg_session, seeded_tenant)
    await pg_session.execute(
        text(
            "INSERT INTO budget_lines (project_id, actual_cents, forecast_cents) "
            "VALUES (:pid, :a, :f)"
        ),
        {"pid": project_id, "a": 110_000_00, "f": 100_000_00},
    )
    await pg_session.commit()

    snapshot = await health_service.snapshot_project_health(pg_session, project_id)
    assert snapshot.score < 100
    assert "budget_variance" in snapshot.factors
    assert snapshot.reasoning is not None

    row = (
        await pg_session.execute(
            text("SELECT health_score, health_computed_at FROM projects WHERE id = :id"),
            {"id": project_id},
        )
    ).one()
    assert row.health_score == snapshot.score
    assert row.health_computed_at is not None


@requires_postgres
async def test_recent_snapshots_returns_history_newest_first(
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    project_id = await _seed_project(pg_session, seeded_tenant)
    for _ in range(3):
        await health_service.snapshot_project_health(pg_session, project_id)

    history = await health_service.recent_snapshots(pg_session, project_id, limit=30)
    assert len(history) == 3
    # Newest first.
    assert history[0].computed_at >= history[-1].computed_at


# --------------------------------------------------------------------------- #
# Router smoke                                                                #
# --------------------------------------------------------------------------- #


@requires_postgres
async def test_get_and_recompute_health_via_http(
    override_auth_and_db: None,
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    del override_auth_and_db

    project_id = await _seed_project(pg_session, seeded_tenant)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # No snapshot yet — GET should 404.
        missing = await client.get(f"/v1/projects/{project_id}/health")
        assert missing.status_code == 404

        # Recompute lands one.
        recomp = await client.post(f"/v1/projects/{project_id}/health/recompute")
        assert recomp.status_code == 201, recomp.text
        assert recomp.json()["score"] == 100

        # Now GET returns it.
        latest = await client.get(f"/v1/projects/{project_id}/health")
        assert latest.status_code == 200
        assert latest.json()["score"] == 100

        # History has one entry.
        hist = await client.get(f"/v1/projects/{project_id}/health/history")
        assert hist.status_code == 200
        assert len(hist.json()) == 1


def test_project_health_router_registered() -> None:
    """Walk both top-level and included routers — see test_risks._all_registered_paths."""
    paths: set[str] = set()
    for rt in app.router.routes:
        path = getattr(rt, "path", None)
        if path:
            paths.add(path)
        original = getattr(rt, "original_router", None)
        if original is not None:
            for child in getattr(original, "routes", []):
                child_path = getattr(child, "path", None)
                if child_path:
                    paths.add(child_path)
    assert "/v1/projects/{project_id}/health" in paths
    assert "/v1/projects/{project_id}/health/recompute" in paths
    assert "/v1/projects/{project_id}/health/history" in paths
