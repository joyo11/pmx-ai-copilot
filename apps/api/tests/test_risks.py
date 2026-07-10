"""Tests for the M2 risk engine.

Covers:

1. Pure-unit factor helpers (LLM response parser). No DB, no HTTP.
2. Integration: rules pass over seeded budget/schedule/RFI/document data,
   verifying each rule fires when the threshold is crossed and stays silent
   otherwise. Requires the test Postgres.
3. Integration: re-scan idempotency — running the scan twice on the same
   underlying condition produces one row per rule_key, not duplicates.
4. Router smoke: list + patch endpoints via ``httpx.AsyncClient``.

LLM calls are patched to skip network; we assert the fallback behaves
(logs, returns []) when ``ANTHROPIC_API_KEY`` is missing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pmx_api.config import Settings
from pmx_api.main import app
from pmx_api.services import risks as risks_service
from tests.conftest import requires_postgres

# --------------------------------------------------------------------------- #
# Pure-unit tests                                                             #
# --------------------------------------------------------------------------- #


def test_parse_llm_response_extracts_tool_use_payload() -> None:
    """The parser should accept both attribute-style and dict-style content blocks."""
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="thinking..."),
            SimpleNamespace(
                type="tool_use",
                name="emit_risks",
                input={
                    "risks": [
                        {
                            "category": "operational",
                            "title": "Weather exposure",
                            "description": "Concrete pours scheduled Feb.",
                            "severity": 3,
                            "likelihood": 0.5,
                            "business_impact": "Cold-weather cost.",
                            "recommended_action": "Reschedule or add heat.",
                            "confidence": 0.7,
                            "citations": [
                                {
                                    "document_id": "doc-1",
                                    "chunk_id": "chunk-1",
                                    "page": 4,
                                }
                            ],
                        }
                    ]
                },
            ),
        ]
    )
    parsed = risks_service._parse_llm_response(response)
    assert len(parsed) == 1
    assert parsed[0].category == "operational"
    assert parsed[0].source == "llm"
    assert parsed[0].rule_key is None
    assert parsed[0].citations[0]["document_id"] == "doc-1"


def test_parse_llm_response_drops_malformed_entries() -> None:
    """Missing required keys → the entry is dropped, others still surface."""
    response = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="tool_use",
                input={
                    "risks": [
                        {"category": "budget"},  # missing everything else
                        {
                            "category": "budget",
                            "title": "OK",
                            "description": "OK",
                            "severity": 2,
                            "likelihood": 0.5,
                            "business_impact": "OK",
                            "recommended_action": "OK",
                            "confidence": 0.5,
                            "citations": [{"document_id": "d", "chunk_id": "c"}],
                        },
                    ]
                },
            )
        ]
    )
    parsed = risks_service._parse_llm_response(response)
    assert len(parsed) == 1
    assert parsed[0].title == "OK"


def test_parse_llm_response_ignores_non_tool_blocks() -> None:
    """Text-only responses (no tool call) return an empty list, not a crash."""
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="I have nothing to add.")]
    )
    assert risks_service._parse_llm_response(response) == []


# --------------------------------------------------------------------------- #
# Rules-pass integration                                                      #
# --------------------------------------------------------------------------- #


async def _seed_project(pg_session: AsyncSession, seeded_tenant: dict[str, uuid.UUID]) -> uuid.UUID:
    project_id = uuid.uuid4()
    await pg_session.execute(
        text("INSERT INTO projects (id, org_id, name) VALUES (:id, :org, :n)"),
        {"id": project_id, "org": seeded_tenant["org_uuid"], "n": "Risk Test"},
    )
    await pg_session.commit()
    return project_id


def _no_key_settings() -> Settings:
    """Settings snapshot with the LLM disabled (matches the CI happy path)."""
    return Settings(anthropic_api_key=None)


@requires_postgres
async def test_rules_pass_flags_budget_overrun(
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    """actual > 1.05x forecast should produce exactly one budget risk."""
    project_id = await _seed_project(pg_session, seeded_tenant)
    await pg_session.execute(
        text(
            "INSERT INTO budget_lines (project_id, category, actual_cents, forecast_cents) "
            "VALUES (:pid, 'concrete', :a, :f)"
        ),
        {"pid": project_id, "a": 150_000_00, "f": 100_000_00},
    )
    await pg_session.commit()

    findings = await risks_service.run_rules(pg_session, project_id)
    budget_hits = [f for f in findings if f.rule_key == "budget_overrun"]
    assert len(budget_hits) == 1
    assert budget_hits[0].category == "budget"
    assert budget_hits[0].severity >= 3


@requires_postgres
async def test_rules_pass_silent_when_forecast_zero(
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    """Zero forecast → no budget finding (avoid divide-by-zero false positive)."""
    project_id = await _seed_project(pg_session, seeded_tenant)
    await pg_session.execute(
        text(
            "INSERT INTO budget_lines (project_id, actual_cents, forecast_cents) "
            "VALUES (:pid, :a, :f)"
        ),
        {"pid": project_id, "a": 100_000_00, "f": 0},
    )
    await pg_session.commit()

    findings = await risks_service.run_rules(pg_session, project_id)
    assert not any(f.rule_key == "budget_overrun" for f in findings)


@requires_postgres
async def test_rules_pass_flags_schedule_slip(
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    """slip_days > 7 → single aggregate schedule risk."""
    project_id = await _seed_project(pg_session, seeded_tenant)
    await pg_session.execute(
        text(
            "INSERT INTO schedule_tasks (project_id, name, slip_days, is_critical) "
            "VALUES (:pid, :n, :s, :c)"
        ),
        [
            {"pid": project_id, "n": "Foundation", "s": 12, "c": True},
            {"pid": project_id, "n": "Rough-in", "s": 3, "c": False},
        ],
    )
    await pg_session.commit()

    findings = await risks_service.run_rules(pg_session, project_id)
    slip_hits = [f for f in findings if f.rule_key == "schedule_slip"]
    assert len(slip_hits) == 1
    # Critical-path slip => severity 4.
    assert slip_hits[0].severity == 4


@requires_postgres
async def test_rules_pass_flags_overdue_rfi(
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    """One risk per RFI open beyond the 14d threshold."""
    project_id = await _seed_project(pg_session, seeded_tenant)
    old = date.today() - timedelta(days=20)
    fresh = date.today() - timedelta(days=3)
    await pg_session.execute(
        text(
            "INSERT INTO rfis (project_id, number, subject, status, submitted_date) "
            "VALUES (:pid, :num, :sub, 'open', :d)"
        ),
        [
            {"pid": project_id, "num": "R-1", "sub": "Old", "d": old},
            {"pid": project_id, "num": "R-2", "sub": "Fresh", "d": fresh},
        ],
    )
    await pg_session.commit()

    findings = await risks_service.run_rules(pg_session, project_id)
    rfi_hits = [f for f in findings if f.rule_key and f.rule_key.startswith("rfi_overdue:")]
    assert len(rfi_hits) == 1
    assert rfi_hits[0].category == "operational"


@requires_postgres
async def test_rules_pass_flags_failed_documents(
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    project_id = await _seed_project(pg_session, seeded_tenant)
    user_uuid = seeded_tenant["user_uuid"]
    await pg_session.execute(
        text(
            "INSERT INTO documents (project_id, uploaded_by, kind, filename, storage_uri, status) "
            "VALUES (:pid, :u, 'pdf_generic', :fn, :uri, 'failed')"
        ),
        {"pid": project_id, "u": user_uuid, "fn": "broken.pdf", "uri": "file:///tmp/broken.pdf"},
    )
    await pg_session.commit()

    findings = await risks_service.run_rules(pg_session, project_id)
    doc_hits = [f for f in findings if f.rule_key == "documents_failed"]
    assert len(doc_hits) == 1


@requires_postgres
async def test_rules_pass_flags_change_order_backlog(
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    project_id = await _seed_project(pg_session, seeded_tenant)
    for i in range(4):
        await pg_session.execute(
            text(
                "INSERT INTO change_orders (project_id, number, amount_cents, status) "
                "VALUES (:pid, :num, :amt, 'pending')"
            ),
            {"pid": project_id, "num": f"CO-{i}", "amt": 10_000_00},
        )
    await pg_session.commit()

    findings = await risks_service.run_rules(pg_session, project_id)
    co_hits = [f for f in findings if f.rule_key == "change_orders_backlog"]
    assert len(co_hits) == 1
    assert co_hits[0].category == "budget"


# --------------------------------------------------------------------------- #
# Scan idempotency                                                            #
# --------------------------------------------------------------------------- #


@requires_postgres
async def test_scan_project_is_idempotent_on_same_condition(
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Running scan_project twice on the same overrun should not duplicate rows."""
    project_id = await _seed_project(pg_session, seeded_tenant)
    await pg_session.execute(
        text(
            "INSERT INTO budget_lines (project_id, actual_cents, forecast_cents) "
            "VALUES (:pid, :a, :f)"
        ),
        {"pid": project_id, "a": 200_000_00, "f": 100_000_00},
    )
    await pg_session.commit()

    # Skip the LLM pass — we're testing rules dedup.
    async def _no_llm(*args: Any, **kwargs: Any) -> list[Any]:
        del args, kwargs
        return []

    monkeypatch.setattr(risks_service, "_call_llm_pass", _no_llm)

    settings = _no_key_settings()
    first = await risks_service.scan_project(pg_session, project_id, settings)
    second = await risks_service.scan_project(pg_session, project_id, settings)

    budget_first_ids = [r.id for r in first if r.metadata_.get("rule_key") == "budget_overrun"]
    budget_second_ids = [r.id for r in second if r.metadata_.get("rule_key") == "budget_overrun"]
    assert len(budget_first_ids) == 1
    assert len(budget_second_ids) == 1
    assert budget_first_ids == budget_second_ids

    # And the risks table has exactly one row for this rule_key.
    row_count = (
        await pg_session.execute(
            text(
                "SELECT COUNT(*) FROM risks "
                "WHERE project_id = :pid "
                "AND (metadata->>'rule_key') = 'budget_overrun'"
            ),
            {"pid": project_id},
        )
    ).scalar_one()
    assert int(row_count) == 1


@requires_postgres
async def test_scan_project_llm_skipped_without_api_key(
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    """Missing ANTHROPIC_API_KEY → LLM pass returns []; rules-only rows land."""
    project_id = await _seed_project(pg_session, seeded_tenant)
    await pg_session.execute(
        text(
            "INSERT INTO budget_lines (project_id, actual_cents, forecast_cents) "
            "VALUES (:pid, :a, :f)"
        ),
        {"pid": project_id, "a": 150_000_00, "f": 100_000_00},
    )
    # Seed a chunk so the LLM pass would otherwise trigger.
    await pg_session.execute(
        text(
            "INSERT INTO document_chunks (project_id, document_id, chunk_index, text) "
            "SELECT :pid, gen_random_uuid(), 0, 'sample text'"
        ),
        {"pid": project_id},
    )
    await pg_session.commit()

    settings = _no_key_settings()
    written = await risks_service.scan_project(pg_session, project_id, settings)
    # Only the rules-based budget row should have landed.
    assert all(r.metadata_.get("source") == "rules" for r in written)


# --------------------------------------------------------------------------- #
# Router smoke                                                                #
# --------------------------------------------------------------------------- #


@requires_postgres
async def test_list_and_patch_risk_via_http(
    override_auth_and_db: None,
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seed a project + rules trigger, scan via HTTP, list, then patch to resolved."""
    del override_auth_and_db

    project_id = await _seed_project(pg_session, seeded_tenant)
    await pg_session.execute(
        text(
            "INSERT INTO budget_lines (project_id, actual_cents, forecast_cents) "
            "VALUES (:pid, :a, :f)"
        ),
        {"pid": project_id, "a": 200_000_00, "f": 100_000_00},
    )
    await pg_session.commit()

    async def _no_llm(*args: Any, **kwargs: Any) -> list[Any]:
        del args, kwargs
        return []

    monkeypatch.setattr(risks_service, "_call_llm_pass", _no_llm)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        scan = await client.post(f"/v1/projects/{project_id}/risks/scan")
        assert scan.status_code == 200, scan.text
        payload = scan.json()
        assert payload["total"] >= 1

        listing = await client.get(f"/v1/projects/{project_id}/risks")
        assert listing.status_code == 200
        rows = listing.json()
        assert any(r["category"] == "budget" for r in rows)
        budget_row = next(r for r in rows if r["category"] == "budget")

        # Detail.
        detail = await client.get(f"/v1/risks/{budget_row['id']}")
        assert detail.status_code == 200
        assert detail.json()["source"] == "rules"

        # Patch to resolved.
        patched = await client.patch(
            f"/v1/risks/{budget_row['id']}",
            json={"status": "resolved"},
        )
        assert patched.status_code == 200
        body = patched.json()
        assert body["status"] == "resolved"
        assert body["resolved_at"] is not None


@requires_postgres
async def test_list_risks_filters_by_status_and_category(
    override_auth_and_db: None,
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    del override_auth_and_db

    project_id = await _seed_project(pg_session, seeded_tenant)
    now = datetime.now(UTC)
    # Two seeded risks: one open budget, one resolved schedule.
    await pg_session.execute(
        text(
            """
            INSERT INTO risks (
              project_id, category, title, description, severity, likelihood,
              business_impact, recommended_action, confidence, status,
              detected_at, metadata
            ) VALUES
              (:pid, 'budget', 't1', 'd1', 3, 0.8, 'bi', 'ra', 0.9,
               'open', :now, '{"rule_key":"seed_budget"}'::jsonb),
              (:pid, 'schedule', 't2', 'd2', 2, 0.5, 'bi', 'ra', 0.7,
               'resolved', :now, '{"rule_key":"seed_schedule"}'::jsonb)
            """
        ),
        {"pid": project_id, "now": now},
    )
    await pg_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Filter to open only.
        r_open = await client.get(f"/v1/projects/{project_id}/risks", params={"status": "open"})
        assert r_open.status_code == 200
        assert {row["category"] for row in r_open.json()} == {"budget"}

        # Filter by category.
        r_cat = await client.get(
            f"/v1/projects/{project_id}/risks", params={"category": "schedule"}
        )
        assert r_cat.status_code == 200
        assert {row["category"] for row in r_cat.json()} == {"schedule"}

        # Filter by severity_gte.
        r_sev = await client.get(f"/v1/projects/{project_id}/risks", params={"severity_gte": 3})
        assert r_sev.status_code == 200
        assert all(row["severity"] >= 3 for row in r_sev.json())


@requires_postgres
async def test_get_risk_404_when_cross_tenant(
    override_auth_and_db: None,
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    """A risk under a project in another org must 404, not leak."""
    del override_auth_and_db, seeded_tenant

    other_org = uuid.uuid4()
    other_project = uuid.uuid4()
    other_risk = uuid.uuid4()
    now = datetime.now(UTC)
    await pg_session.execute(
        text("INSERT INTO organizations (id, clerk_org_id, name) VALUES (:id, :cid, :n)"),
        {"id": other_org, "cid": "org_isolated", "n": "Other"},
    )
    await pg_session.execute(
        text("INSERT INTO projects (id, org_id, name) VALUES (:id, :org, :n)"),
        {"id": other_project, "org": other_org, "n": "Secret"},
    )
    await pg_session.execute(
        text(
            """
            INSERT INTO risks (
              id, project_id, category, title, description, severity, likelihood,
              business_impact, recommended_action, confidence, detected_at
            ) VALUES (
              :id, :pid, 'budget', 'x', 'x', 1, 0.5, 'x', 'x', 0.5, :now
            )
            """
        ),
        {"id": other_risk, "pid": other_project, "now": now},
    )
    await pg_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/v1/risks/{other_risk}")
        assert resp.status_code == 404


def _all_registered_paths() -> set[str]:
    """Walk nested routers — FastAPI wraps includes in ``_IncludedRouter``
    which no longer exposes ``routes`` directly (behaviour changed in the
    fastapi bundled with this repo). We hop through ``original_router`` to
    reach the leaf ``APIRoute`` instances.
    """
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
    return paths


def test_risks_router_registered() -> None:
    """Import-level check: main.py wires the risks router."""
    paths = _all_registered_paths()
    assert "/v1/projects/{project_id}/risks" in paths
    assert "/v1/projects/{project_id}/risks/scan" in paths
    assert "/v1/risks/{risk_id}" in paths
