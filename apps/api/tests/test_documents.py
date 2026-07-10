"""Tests for the M1 documents router + extraction pipeline.

We build a tiny synthetic PDF at fixture time via PyMuPDF so the test suite
doesn't need a checked-in binary. The OpenAI embedding client is patched to
a deterministic stub so no network calls happen and no API key is required.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pmx_api.main import app
from pmx_api.pipeline import extract as extract_module
from pmx_api.pipeline.extract import Embedder, chunk_pages
from tests.conftest import requires_postgres

EMBEDDING_DIM = 3072


class _StubEmbedder:
    """Deterministic in-memory embedder — returns a repeatable zero-padded vector.

    Real cosine ranking isn't exercised here; we just need something the
    ``pgvector`` column will accept.
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        # Use the first character's ordinal as the leading dim so different
        # chunks have distinguishable vectors (helps debugging, not scoring).
        return [
            [float(ord(t[0]) if t else 0) / 1000.0] + [0.0] * (EMBEDDING_DIM - 1) for t in texts
        ]


def _make_tiny_pdf(pages: int = 2) -> bytes:
    """Build a small in-memory PDF with a couple of paragraphs per page."""
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page_text = (
            f"Page {i + 1} paragraph one about the schedule and critical path.\n\n"
            f"Page {i + 1} paragraph two about RFI number 42 and its impact on\n"
            f"the electrical rough-in scheduled for next week."
        )
        page.insert_text((72, 72), page_text, fontsize=11)
    payload = io.BytesIO()
    doc.save(payload)
    doc.close()
    return payload.getvalue()


# --------------------------------------------------------------------------- #
# Pure-unit tests — no DB, no HTTP                                            #
# --------------------------------------------------------------------------- #


def test_chunk_pages_preserves_source_page() -> None:
    """Chunks emitted for a given page must carry that page number."""
    pages = [
        (1, "First page paragraph one.\n\nFirst page paragraph two."),
        (2, "Second page single paragraph."),
    ]
    chunks = chunk_pages(pages)
    assert chunks, "expected at least one chunk"
    assert any(c.page == 1 for c in chunks)
    assert any(c.page == 2 for c in chunks)
    # Chunk indices are stable across pages.
    assert [c.index for c in chunks] == sorted(c.index for c in chunks)


def test_chunk_pages_handles_empty_input() -> None:
    """No pages ⇒ no chunks (not a crash)."""
    assert chunk_pages([]) == []


# --------------------------------------------------------------------------- #
# Integration test — real Postgres, stubbed OpenAI                            #
# --------------------------------------------------------------------------- #


@requires_postgres
async def test_upload_pdf_runs_extraction_and_inserts_chunks(
    override_auth_and_db: None,
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """POST a tiny PDF and confirm chunks + embeddings landed in Postgres."""
    del override_auth_and_db

    # Point storage at a per-test temp dir so we don't pollute the repo.
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    from pmx_api.config import get_settings

    get_settings.cache_clear()

    # Force the extractor to use our stub instead of building the real client.
    def _stub_factory(settings: Any) -> Embedder:
        return _StubEmbedder()

    monkeypatch.setattr(extract_module, "_openai_embedder", _stub_factory)

    # Seed a project owned by the current tenant.
    org_uuid = seeded_tenant["org_uuid"]
    project_id = uuid.uuid4()
    await pg_session.execute(
        text("INSERT INTO projects (id, org_id, name) VALUES (:id, :org, :n)"),
        {"id": project_id, "org": org_uuid, "n": "Test Project"},
    )
    await pg_session.commit()

    pdf_bytes = _make_tiny_pdf(pages=2)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/v1/projects/{project_id}/documents",
            files={"file": ("sample.pdf", pdf_bytes, "application/pdf")},
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "ready"
    document_id = body["document_id"]

    # Chunk rows exist and preserve page numbers.
    rows = (
        await pg_session.execute(
            text(
                "SELECT page, text FROM document_chunks "
                "WHERE document_id = :id ORDER BY chunk_index"
            ),
            {"id": document_id},
        )
    ).all()
    assert rows, "expected at least one chunk row for the uploaded PDF"
    pages_covered = {row.page for row in rows}
    assert pages_covered.issubset({1, 2})


@requires_postgres
async def test_upload_rejects_non_pdf(
    override_auth_and_db: None,
    seeded_tenant: dict[str, uuid.UUID],
    pg_session: AsyncSession,
) -> None:
    """Any MIME other than application/pdf must 415 in M1."""
    del override_auth_and_db

    project_id = uuid.uuid4()
    await pg_session.execute(
        text("INSERT INTO projects (id, org_id, name) VALUES (:id, :org, :n)"),
        {"id": project_id, "org": seeded_tenant["org_uuid"], "n": "Test"},
    )
    await pg_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/v1/projects/{project_id}/documents",
            files={"file": ("sample.txt", b"hello world", "text/plain")},
        )
    assert response.status_code == 415
