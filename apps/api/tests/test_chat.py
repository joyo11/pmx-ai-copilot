"""Tests for the M1 chat router.

Retrieval + Anthropic streaming are both patched so we can verify the SSE
event ordering deterministically without touching the network or the DB.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pmx_api.main import app
from pmx_api.pipeline.retrieve import RetrievedChunk
from pmx_api.routers import chat as chat_module
from tests.conftest import requires_postgres


def _parse_sse(payload: str) -> list[tuple[str, str]]:
    """Break an SSE payload into ``[(event, data), ...]``.

    Simplified parser: we know sse-starlette emits ``event: X\\r\\ndata: Y\\r\\n\\r\\n``
    (or with LF endings depending on version). This suffices for the assertions
    below.
    """
    events: list[tuple[str, str]] = []
    current_event: str | None = None
    current_data: list[str] = []

    def flush() -> None:
        nonlocal current_event, current_data
        if current_event is not None:
            events.append((current_event, "".join(current_data)))
        current_event = None
        current_data = []

    for raw_line in payload.replace("\r\n", "\n").split("\n"):
        line = raw_line.rstrip("\r")
        if not line:
            flush()
            continue
        if line.startswith("event:"):
            current_event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            current_data.append(line.removeprefix("data:").strip())
    flush()
    return events


@requires_postgres
async def test_chat_emits_citation_then_token_then_done(
    override_auth_and_db: None,
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SSE order: all citations, then tokens in-order, then one done event."""
    del override_auth_and_db

    # Seed a project so the auth+scope checks pass.
    project_id = uuid.uuid4()
    await pg_session.execute(
        text("INSERT INTO projects (id, org_id, name) VALUES (:id, :org, :n)"),
        {"id": project_id, "org": seeded_tenant["org_uuid"], "n": "P"},
    )
    await pg_session.commit()

    fake_chunks = [
        RetrievedChunk(
            chunk_id=str(uuid.uuid4()),
            document_id=str(uuid.uuid4()),
            project_id=str(project_id),
            page=3,
            text="Chunk about slab pour scheduling.",
            distance=0.12,
        ),
        RetrievedChunk(
            chunk_id=str(uuid.uuid4()),
            document_id=str(uuid.uuid4()),
            project_id=str(project_id),
            page=7,
            text="Chunk about RFI turnaround.",
            distance=0.18,
        ),
    ]

    async def _fake_embed(query: str, settings: Any) -> list[float]:
        del query, settings
        return [0.0] * 3072

    async def _fake_retrieve(
        db: Any,
        project_id: Any,
        query_embedding: Any,
        top_k: int,
    ) -> list[RetrievedChunk]:
        del db, project_id, query_embedding, top_k
        return fake_chunks

    async def _fake_stream(
        *,
        settings: Any,
        user_message: str,
        excerpts: Any,
    ) -> AsyncIterator[str]:
        del settings, user_message, excerpts
        for piece in ["Hello", " ", "world", " (p.3)"]:
            yield piece

    monkeypatch.setattr(chat_module, "_embed_query", _fake_embed)
    monkeypatch.setattr(chat_module, "retrieve_top_k", _fake_retrieve)
    monkeypatch.setattr(chat_module, "_stream_claude", _fake_stream)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:  # noqa: SIM117
        async with client.stream(
            "POST",
            f"/v1/projects/{project_id}/chat",
            json={"message": "When is the slab pour?"},
        ) as response:
            assert response.status_code == 200
            body = b"".join([chunk async for chunk in response.aiter_bytes()]).decode()

    events = _parse_sse(body)
    kinds = [e[0] for e in events]

    # Citations come first — one per retrieved chunk.
    assert kinds[:2] == ["citation", "citation"], events
    # Then tokens in order.
    token_events = [e for e in events if e[0] == "token"]
    assert len(token_events) == 4
    # Finally a single done event with the session id.
    assert kinds[-1] == "done"
    assert '"session_id"' in events[-1][1]


@requires_postgres
async def test_chat_reports_error_event_on_stream_failure(
    override_auth_and_db: None,
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A crash inside the Claude stream must surface as an ``error`` SSE event."""
    del override_auth_and_db

    project_id = uuid.uuid4()
    await pg_session.execute(
        text("INSERT INTO projects (id, org_id, name) VALUES (:id, :org, :n)"),
        {"id": project_id, "org": seeded_tenant["org_uuid"], "n": "P"},
    )
    await pg_session.commit()

    async def _fake_embed(query: str, settings: Any) -> list[float]:
        del query, settings
        return [0.0] * 3072

    async def _fake_retrieve(*args: Any, **kwargs: Any) -> list[RetrievedChunk]:
        del args, kwargs
        return []

    async def _broken_stream(**_: Any) -> AsyncIterator[str]:
        raise RuntimeError("upstream boom")
        yield ""  # pragma: no cover — required to make this an async generator

    monkeypatch.setattr(chat_module, "_embed_query", _fake_embed)
    monkeypatch.setattr(chat_module, "retrieve_top_k", _fake_retrieve)
    monkeypatch.setattr(chat_module, "_stream_claude", _broken_stream)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:  # noqa: SIM117
        async with client.stream(
            "POST",
            f"/v1/projects/{project_id}/chat",
            json={"message": "Whatever"},
        ) as response:
            assert response.status_code == 200
            body = b"".join([chunk async for chunk in response.aiter_bytes()]).decode()

    events = _parse_sse(body)
    assert any(kind == "error" for kind, _ in events), events
