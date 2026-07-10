"""PDF extraction + chunking + embedding pipeline (M1 scope).

Flow:

1. ``fitz`` walks the PDF page-by-page, capturing text + source page number.
2. Text is dumped as-is to ``{storage_dir}/{document_id}.txt`` for later reuse
   (structured extractors in M2 will re-parse this rather than the PDF).
3. Chunker splits the per-page text into ~1000-token paragraphs with ~100 tokens
   of overlap, preserving the source page number on every chunk. Tokens are
   estimated as ``len(text) // 4`` — cheap and good enough for chunk sizing;
   we don't need exact BPE math here.
4. Chunks embedded via OpenAI ``text-embedding-3-large`` in batches of 100.
5. Rows written to ``document_chunks`` with the ``pgvector`` embedding column
   populated. Document status transitions ``uploaded -> extracting -> embedding
   -> ready`` (or ``failed`` with error text).

M1 runs this synchronously from the upload handler. M2 hands the same function
to an RQ worker without any signature change.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from pmx_api.config import Settings
from pmx_api.db.models import Document, DocumentChunk

logger = logging.getLogger(__name__)

# Chunking parameters — see DESIGN §11 "Chunk size" trade-off row.
TARGET_TOKENS_PER_CHUNK = 1000
CHUNK_OVERLAP_TOKENS = 100
_CHARS_PER_TOKEN = 4  # rough approximation, adequate for chunk sizing

# OpenAI's embeddings endpoint accepts up to ~2048 inputs per call; we stay
# well below that (batch of 100) so the request stays snappy and any single
# retryable failure only re-does a small slice.
EMBED_BATCH_SIZE = 100


# --------------------------------------------------------------------------- #
# Data types                                                                  #
# --------------------------------------------------------------------------- #


@dataclass(slots=True, frozen=True)
class Chunk:
    """A single retrieval-ready slice of a document."""

    index: int
    text: str
    page: int


# --------------------------------------------------------------------------- #
# Embedder protocol — makes mocking trivial in tests                          #
# --------------------------------------------------------------------------- #


class Embedder(Protocol):
    """Anything that can turn a batch of strings into embeddings.

    Kept as a Protocol so tests can pass an in-memory stub instead of the real
    OpenAI client. The concrete impl lives in :func:`_openai_embedder`.
    """

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _openai_embedder(settings: Settings) -> Embedder:
    """Build the real OpenAI-backed embedder.

    Isolated in a helper so tests can bypass the API-key gate entirely.
    """
    from openai import OpenAI

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set; cannot embed chunks.")
    client = OpenAI(api_key=settings.openai_api_key)
    model = settings.embedding_model

    class _OpenAIEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            response = client.embeddings.create(model=model, input=texts)
            return [item.embedding for item in response.data]

    return _OpenAIEmbedder()


# --------------------------------------------------------------------------- #
# PDF extraction                                                              #
# --------------------------------------------------------------------------- #


def _extract_pdf_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """Return ``[(page_number_1_indexed, text), ...]`` for every page."""
    import fitz  # PyMuPDF

    pages: list[tuple[int, str]] = []
    with fitz.open(pdf_path) as doc:
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            text = cast(str, page.get_text("text"))
            pages.append((page_index + 1, text))
    return pages


# --------------------------------------------------------------------------- #
# Chunker                                                                     #
# --------------------------------------------------------------------------- #


def _split_paragraphs(text: str) -> list[str]:
    """Split on blank lines; strip; drop empties."""
    return [para.strip() for para in text.split("\n\n") if para.strip()]


def _chunk_page_text(
    page: int,
    text: str,
    start_index: int,
    target_chars: int,
    overlap_chars: int,
) -> list[Chunk]:
    """Greedy paragraph packer with character-level overlap.

    We pack paragraphs into a running buffer until it exceeds ``target_chars``,
    emit the chunk, and re-seed the next chunk with the tail ``overlap_chars``
    of the last one. Chunks never span pages — the caller re-runs this per
    page so ``page`` is preserved on every emitted chunk.
    """
    if not text.strip():
        return []

    chunks: list[Chunk] = []
    buffer = ""
    idx = start_index

    for paragraph in _split_paragraphs(text):
        candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        if len(candidate) >= target_chars:
            # Flush the current buffer as a chunk if it has content.
            if buffer:
                chunks.append(Chunk(index=idx, text=buffer, page=page))
                idx += 1
                # Carry over the tail so context bridges chunk boundaries.
                tail = buffer[-overlap_chars:] if overlap_chars > 0 else ""
                buffer = f"{tail}\n\n{paragraph}" if tail else paragraph
            else:
                # A single paragraph blew past target_chars on its own.
                # Emit it as its own chunk; splitting mid-paragraph would hurt
                # retrieval more than an oversized chunk.
                chunks.append(Chunk(index=idx, text=paragraph, page=page))
                idx += 1
                buffer = ""
        else:
            buffer = candidate

    if buffer:
        chunks.append(Chunk(index=idx, text=buffer, page=page))

    return chunks


def chunk_pages(pages: list[tuple[int, str]]) -> list[Chunk]:
    """Chunk every page independently. Preserves ``page`` on each chunk."""
    target_chars = TARGET_TOKENS_PER_CHUNK * _CHARS_PER_TOKEN
    overlap_chars = CHUNK_OVERLAP_TOKENS * _CHARS_PER_TOKEN

    all_chunks: list[Chunk] = []
    next_index = 0
    for page, text in pages:
        page_chunks = _chunk_page_text(
            page=page,
            text=text,
            start_index=next_index,
            target_chars=target_chars,
            overlap_chars=overlap_chars,
        )
        all_chunks.extend(page_chunks)
        next_index += len(page_chunks)
    return all_chunks


# --------------------------------------------------------------------------- #
# Orchestrator                                                                #
# --------------------------------------------------------------------------- #


async def _set_status(
    db: AsyncSession,
    document_id: uuid.UUID,
    status_value: str,
    error: str | None = None,
) -> None:
    values: dict[str, object] = {"status": status_value}
    if status_value == "ready":
        values["processed_at"] = datetime.now(UTC)
    if error is not None:
        values["error"] = error
    await db.execute(update(Document).where(Document.id == document_id).values(**values))
    await db.commit()


async def extract_and_embed_document(
    *,
    db: AsyncSession,
    document_id: uuid.UUID,
    project_id: uuid.UUID,
    pdf_path: Path,
    settings: Settings,
    embedder: Embedder | None = None,
) -> int:
    """Run the full pipeline for one document. Returns the number of chunks inserted.

    ``embedder`` is dependency-injected so tests can pass a stub. When None,
    we build the real OpenAI-backed embedder.
    """
    used_embedder = embedder or _openai_embedder(settings)

    # 1) Extract.
    await _set_status(db, document_id, "extracting")
    try:
        pages = _extract_pdf_pages(pdf_path)
    except Exception as exc:
        await _set_status(db, document_id, "failed", error=f"extract: {exc}")
        raise

    # 2) Persist the flat text blob for future re-parsing (schedule/budget in M2).
    text_path = pdf_path.with_suffix(".txt")
    combined_text = "\n\n".join(text for _, text in pages)
    text_path.write_text(combined_text, encoding="utf-8")
    await db.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(extracted_text_uri=f"file://{text_path.resolve()}")
    )
    await db.commit()

    # 3) Chunk.
    chunks = chunk_pages(pages)
    if not chunks:
        # Empty PDF — mark ready with zero chunks rather than failing. A PM
        # might upload a cover sheet PDF; not an error.
        await _set_status(db, document_id, "ready")
        return 0

    # 4) Embed in batches.
    await _set_status(db, document_id, "embedding")
    embeddings: list[list[float]] = []
    for start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[start : start + EMBED_BATCH_SIZE]
        try:
            batch_embeddings = used_embedder.embed([c.text for c in batch])
        except Exception as exc:
            await _set_status(db, document_id, "failed", error=f"embed: {exc}")
            raise
        embeddings.extend(batch_embeddings)

    # 5) Insert chunk rows.
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        db.add(
            DocumentChunk(
                document_id=document_id,
                project_id=project_id,
                chunk_index=chunk.index,
                text=chunk.text,
                page=chunk.page,
                embedding=embedding,
            )
        )
    await db.commit()

    await _set_status(db, document_id, "ready")
    logger.info(
        "Extracted %d chunks from document %s across %d pages",
        len(chunks),
        document_id,
        len(pages),
    )
    return len(chunks)
