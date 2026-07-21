"""Tests for the M3 Meeting Intelligence router.

Coverage:

1. Pure-unit — the LLM response parser tolerates attribute-style and
   dict-style blocks, drops malformed rows, and degrades gracefully when
   the LLM never calls the tool.
2. Router smoke over real Postgres:
   * JSON body → analyze → row inserted, action items shape correct,
     risks_created matches ``risks_surfaced`` count.
   * ``list_meetings`` returns the inserted row.
   * ``get_meeting`` returns the structured detail.
3. Missing ``ANTHROPIC_API_KEY`` returns a 503 with a friendly message
   (not a crash).

Every LLM call is monkeypatched — no network, no key required.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pmx_api.main import app
from pmx_api.routers import meetings as meetings_router
from tests.conftest import requires_postgres

# --------------------------------------------------------------------------- #
# Pure-unit tests                                                             #
# --------------------------------------------------------------------------- #


def _sample_payload() -> dict[str, Any]:
    return {
        "summary": (
            "The team reviewed the concrete pour schedule and agreed to move "
            "the north foundation pour to next Tuesday.\n\n"
            "Bob raised an RFI about the rebar spacing that the design team "
            "still hasn't answered."
        ),
        "action_items": [
            {
                "text": "Confirm rebar spacing with structural engineer",
                "owner": "Bob",
                "due_date": "2026-07-15",
            },
            {
                "text": "Update lookahead schedule",
                "owner": "Alice",
                "due_date": "",
            },
        ],
        "decisions": [
            {
                "text": "Move north foundation pour to Tuesday",
                "made_by": "PM Alice",
            }
        ],
        "risks_surfaced": [
            {
                "text": "Rebar RFI still unanswered — may delay concrete pour",
                "category": "schedule",
                "severity_1_to_5": 3,
            }
        ],
    }


def test_parse_llm_response_extracts_tool_use_payload() -> None:
    """Real-shape SimpleNamespace tool-use block → full MeetingAnalysis."""
    payload = _sample_payload()
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="analysing..."),
            SimpleNamespace(type="tool_use", name="emit_meeting_analysis", input=payload),
        ]
    )
    analysis = meetings_router._parse_llm_response(response)

    assert "concrete pour" in analysis.summary
    assert len(analysis.action_items) == 2
    assert analysis.action_items[0].owner == "Bob"
    assert analysis.action_items[0].due_date == "2026-07-15"
    assert analysis.action_items[0].done is False
    assert len(analysis.decisions) == 1
    assert analysis.decisions[0].made_by == "PM Alice"
    assert len(analysis.risks_surfaced) == 1
    assert analysis.risks_surfaced[0].category == "schedule"
    assert analysis.risks_surfaced[0].severity_1_to_5 == 3


def test_parse_llm_response_drops_malformed_entries() -> None:
    """Bad rows get skipped; good rows still surface."""
    response = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="tool_use",
                input={
                    "summary": "OK",
                    "action_items": [
                        "not a dict",
                        {"text": "Good", "owner": "", "due_date": ""},
                    ],
                    "decisions": [{"text": "Fine", "made_by": ""}],
                    "risks_surfaced": [
                        {"text": "vague", "category": "not_a_category", "severity_1_to_5": 99}
                    ],
                },
            )
        ]
    )
    analysis = meetings_router._parse_llm_response(response)
    assert len(analysis.action_items) == 1
    assert analysis.action_items[0].text == "Good"
    # Invalid category falls back to 'operational'; severity clamps to 5.
    assert analysis.risks_surfaced[0].category == "operational"
    assert analysis.risks_surfaced[0].severity_1_to_5 == 5


def test_parse_llm_response_handles_no_tool_call() -> None:
    """LLM answered in plain text → we return an empty analysis, not a crash."""
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="I couldn't parse this transcript.")]
    )
    analysis = meetings_router._parse_llm_response(response)
    assert analysis.summary.startswith("(No structured")
    assert analysis.action_items == []
    assert analysis.decisions == []
    assert analysis.risks_surfaced == []


# --------------------------------------------------------------------------- #
# Router integration                                                          #
# --------------------------------------------------------------------------- #


async def _seed_project(pg_session: AsyncSession, seeded_tenant: dict[str, uuid.UUID]) -> uuid.UUID:
    project_id = uuid.uuid4()
    await pg_session.execute(
        text("INSERT INTO projects (id, org_id, name) VALUES (:id, :org, :n)"),
        {"id": project_id, "org": seeded_tenant["org_uuid"], "n": "Meeting Test"},
    )
    await pg_session.commit()
    return project_id


def _fake_analyze_factory(
    payload: dict[str, Any] | None = None,
) -> Any:
    """Build a stand-in for ``_call_llm_analyze`` that returns a fixed analysis."""
    body = payload if payload is not None else _sample_payload()

    async def _fake(**kwargs: Any) -> meetings_router.MeetingAnalysis:
        del kwargs
        return meetings_router._payload_to_analysis(body)

    return _fake


@requires_postgres
async def test_analyze_meeting_via_json_persists_and_returns_shape(
    override_auth_and_db: None,
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST JSON body → meeting row + risks rows land; response shape is right."""
    del override_auth_and_db

    project_id = await _seed_project(pg_session, seeded_tenant)
    monkeypatch.setattr(meetings_router, "_call_llm_analyze", _fake_analyze_factory())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/v1/projects/{project_id}/meetings/analyze",
            json={
                "transcript_text": (
                    "Alice: Let's start. Bob, how's the RFI?\n"
                    "Bob: Still waiting on structural.\n"
                    "Alice: We'll move the pour."
                ),
                "meeting_date": "2026-07-10",
            },
        )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["meeting_id"]
    assert "concrete pour" in body["summary"]
    assert len(body["action_items"]) == 2
    assert body["action_items"][0]["done"] is False
    assert body["risks_created"] == 1

    # Meeting row landed.
    row = (
        await pg_session.execute(
            text(
                "SELECT summary, meeting_date, action_items, decisions FROM meetings WHERE id = :id"
            ),
            {"id": body["meeting_id"]},
        )
    ).one()
    assert row.summary is not None
    assert str(row.meeting_date) == "2026-07-10"
    # JSONB round-trips as list[dict].
    assert isinstance(row.action_items, list)
    assert len(row.action_items) == 2
    assert row.action_items[0]["text"].startswith("Confirm rebar")
    assert isinstance(row.decisions, list)
    assert len(row.decisions) == 1

    # Risk row was created and tagged to this meeting.
    risk_count = (
        await pg_session.execute(
            text(
                "SELECT COUNT(*) FROM risks "
                "WHERE project_id = :pid "
                "AND (metadata->>'meeting_id') = :mid"
            ),
            {"pid": project_id, "mid": body["meeting_id"]},
        )
    ).scalar_one()
    assert int(risk_count) == 1


@requires_postgres
async def test_analyze_meeting_via_multipart_txt(
    override_auth_and_db: None,
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uploading a .txt file works and pulls in optional meeting_date form field."""
    del override_auth_and_db

    project_id = await _seed_project(pg_session, seeded_tenant)
    monkeypatch.setattr(meetings_router, "_call_llm_analyze", _fake_analyze_factory())

    transcript = b"Attendees: Alice, Bob\n\nDiscussion of concrete pour."

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/v1/projects/{project_id}/meetings/analyze",
            files={"file": ("meeting.txt", transcript, "text/plain")},
            data={"meeting_date": "2026-07-08"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    row = (
        await pg_session.execute(
            text("SELECT meeting_date FROM meetings WHERE id = :id"),
            {"id": body["meeting_id"]},
        )
    ).one()
    assert str(row.meeting_date) == "2026-07-08"


@requires_postgres
async def test_list_and_get_meeting(
    override_auth_and_db: None,
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Analyze once, list returns it, detail returns the structured shape."""
    del override_auth_and_db

    project_id = await _seed_project(pg_session, seeded_tenant)
    monkeypatch.setattr(meetings_router, "_call_llm_analyze", _fake_analyze_factory())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        create = await client.post(
            f"/v1/projects/{project_id}/meetings/analyze",
            json={"transcript_text": "Short transcript for testing."},
        )
        assert create.status_code == 200
        meeting_id = create.json()["meeting_id"]

        listing = await client.get(f"/v1/projects/{project_id}/meetings")
        assert listing.status_code == 200
        rows = listing.json()
        assert any(r["id"] == meeting_id for r in rows)
        row = next(r for r in rows if r["id"] == meeting_id)
        assert row["action_item_count"] == 2
        assert row["decision_count"] == 1

        detail = await client.get(f"/v1/meetings/{meeting_id}")
        assert detail.status_code == 200
        d = detail.json()
        assert len(d["action_items"]) == 2
        assert d["action_items"][0]["done"] is False
        assert len(d["decisions"]) == 1


@requires_postgres
async def test_analyze_returns_503_without_anthropic_key(
    override_auth_and_db: None,
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing ANTHROPIC_API_KEY → friendly 503, not a 500 stack trace."""
    del override_auth_and_db

    project_id = await _seed_project(pg_session, seeded_tenant)

    # Swap the settings dep for one that always reports no key, regardless
    # of what's in the process env.
    from pmx_api.config import Settings, get_settings

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def _no_key_settings() -> Settings:
        s = Settings()
        s.anthropic_api_key = None
        return s

    app.dependency_overrides[get_settings] = _no_key_settings
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/v1/projects/{project_id}/meetings/analyze",
                json={"transcript_text": "hello"},
            )
        assert resp.status_code == 503, resp.text
        assert "ANTHROPIC_API_KEY" in resp.text
    finally:
        app.dependency_overrides.pop(get_settings, None)


@requires_postgres
async def test_analyze_rejects_empty_transcript(
    override_auth_and_db: None,
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    """Empty body → 400 before hitting the LLM."""
    del override_auth_and_db  # fixture side-effect

    project_id = await _seed_project(pg_session, seeded_tenant)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/v1/projects/{project_id}/meetings/analyze",
            json={"transcript_text": "   \n  "},
        )
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# Registration                                                                #
# --------------------------------------------------------------------------- #


def _all_registered_paths() -> set[str]:
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


def test_meetings_router_registered() -> None:
    paths = _all_registered_paths()
    assert "/v1/projects/{project_id}/meetings" in paths
    assert "/v1/projects/{project_id}/meetings/analyze" in paths
    assert "/v1/meetings/{meeting_id}" in paths
