"""Retrieval — top-k nearest chunks for a query, scoped to a project.

Uses ``pgvector``'s cosine distance operator (``<=>``). We keep this in a
dedicated module so the chat router stays HTTP-only, and so the same helper
serves the risk engine in M2 without churn.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(slots=True, frozen=True)
class RetrievedChunk:
    """One retrieved chunk ready for prompting + citation."""

    chunk_id: str
    document_id: str
    project_id: str
    page: int | None
    text: str
    distance: float


async def retrieve_top_k(
    db: AsyncSession,
    project_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int,
) -> list[RetrievedChunk]:
    """Return the ``top_k`` chunks nearest to ``query_embedding`` in the project.

    Uses cosine distance (``<=>``). The HNSW index on ``document_chunks.embedding``
    covers this operator per DESIGN §4.
    """
    # We pass the vector literal as a string parameter and cast it inside SQL
    # so we don't need to import pgvector's parameter binder here (keeping this
    # module dependency-free apart from SQLAlchemy).
    vector_literal = "[" + ",".join(f"{v:.8f}" for v in query_embedding) + "]"

    rows = (
        await db.execute(
            text(
                """
                SELECT id, document_id, project_id, page, text,
                       embedding <=> CAST(:query_vec AS vector) AS distance
                FROM document_chunks
                WHERE project_id = :project_id
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> CAST(:query_vec AS vector)
                LIMIT :top_k
                """
            ),
            {
                "query_vec": vector_literal,
                "project_id": project_id,
                "top_k": top_k,
            },
        )
    ).all()

    return [
        RetrievedChunk(
            chunk_id=str(row.id),
            document_id=str(row.document_id),
            project_id=str(row.project_id),
            page=row.page,
            text=row.text,
            distance=float(row.distance),
        )
        for row in rows
    ]
