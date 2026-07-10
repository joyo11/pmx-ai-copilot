"""Chat with retrieval + citations, streamed over SSE (M1 scope).

Wire contract (matches DESIGN §5 "Streaming convention"):

* ``event: token``   ``data: {"text": "..."}``    — partial tokens.
* ``event: citation`` ``data: {"document_id","chunk_id","page"}`` — sources.
* ``event: done``    ``data: {"session_id": "..."}`` — final marker.
* ``event: error``   ``data: {"message": "..."}``  — anything that blew up.

We emit **all citations up front** (before token streaming starts) so the
frontend can render the Sources panel while tokens fill in. That's simpler
than teaching the model to interleave citation markers mid-stream, and it
preserves the "every claim cites (p.N)" contract in the prose.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from pmx_api.config import Settings, get_settings
from pmx_api.db.models import ChatMessage, ChatSession, Project
from pmx_api.deps import (
    CurrentUser,
    DBSession,
    require_current_user,
    resolve_tenant,
)
from pmx_api.pipeline.retrieve import RetrievedChunk, retrieve_top_k

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/projects/{project_id}/chat", tags=["chat"])

SYSTEM_PROMPT = (
    "You are a construction project management copilot. Answer using ONLY the "
    "provided document excerpts. Cite the page number for every claim in the "
    "form (p.N). If the answer isn't in the excerpts, say so."
)


# --------------------------------------------------------------------------- #
# Schemas                                                                     #
# --------------------------------------------------------------------------- #


class ChatRequest(BaseModel):
    """Body for a chat turn.

    ``session_id`` is optional — omit it to start a new session. When the SSE
    stream closes we emit the resolved id back so the client can pin it.
    """

    message: str = Field(min_length=1)
    session_id: str | None = None


# --------------------------------------------------------------------------- #
# Injectable seams for tests                                                  #
# --------------------------------------------------------------------------- #


async def _embed_query(query: str, settings: Settings) -> list[float]:
    """Embed the user's message with the configured OpenAI model.

    Tests monkeypatch this module attribute directly to skip the network call.
    """
    from openai import OpenAI

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set; cannot embed query.")
    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.embeddings.create(model=settings.embedding_model, input=[query])
    return list(resp.data[0].embedding)


async def _stream_claude(
    *,
    settings: Settings,
    user_message: str,
    excerpts: list[RetrievedChunk],
) -> AsyncIterator[str]:
    """Stream token deltas from Anthropic's messages API.

    Yields raw text fragments. Tests monkeypatch this to yield a fixed sequence.
    """
    from anthropic import AsyncAnthropic

    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set; cannot answer chat.")
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    excerpt_block = (
        "\n\n".join(
            f"[chunk {i + 1}, p.{chunk.page}] {chunk.text}" for i, chunk in enumerate(excerpts)
        )
        or "(no relevant excerpts found)"
    )

    prompt = (
        f"Document excerpts follow. Answer the question using only these.\n\n"
        f"{excerpt_block}\n\n"
        f"Question: {user_message}"
    )

    async with client.messages.stream(
        model=settings.chat_model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        async for text_delta in stream.text_stream:
            yield text_delta


# --------------------------------------------------------------------------- #
# SSE event builders                                                          #
# --------------------------------------------------------------------------- #


def _sse(event: str, payload: dict[str, Any]) -> dict[str, str]:
    """Shape a payload for sse-starlette's ``EventSourceResponse``."""
    return {"event": event, "data": json.dumps(payload)}


# --------------------------------------------------------------------------- #
# Route                                                                       #
# --------------------------------------------------------------------------- #


@router.post(
    "",
    summary="Chat with a project (SSE: token / citation / done / error)",
    response_class=EventSourceResponse,
)
async def chat(
    project_id: uuid.UUID,
    body: ChatRequest,
    request: Request,
    db: DBSession,
    current: Annotated[CurrentUser, Depends(require_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EventSourceResponse:
    tenant = await resolve_tenant(db, current)

    project = (
        await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.org_id == uuid.UUID(tenant.org_uuid),
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Resolve or create the session up front so the ``done`` event and the
    # persisted user message share the same id.
    session_id: uuid.UUID | None = None
    if body.session_id:
        try:
            candidate = uuid.UUID(body.session_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid session_id",
            ) from exc
        session = (
            await db.execute(
                select(ChatSession).where(
                    ChatSession.id == candidate,
                    ChatSession.user_id == uuid.UUID(tenant.user_uuid),
                )
            )
        ).scalar_one_or_none()
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found",
            )
        session_id = session.id
    else:
        session = ChatSession(
            user_id=uuid.UUID(tenant.user_uuid),
            project_id=project.id,
            title=body.message[:80],
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        session_id = session.id

    # Persist the user message before we start streaming so it survives a
    # client disconnect mid-response.
    db.add(
        ChatMessage(
            session_id=session_id,
            role="user",
            content=body.message,
        )
    )
    await db.commit()

    # Retrieve excerpts synchronously — we need them before the stream starts
    # so we can emit ``citation`` events up front.
    try:
        query_embedding = await _embed_query(body.message, settings)
        excerpts = await retrieve_top_k(
            db,
            project_id=project.id,
            query_embedding=query_embedding,
            top_k=settings.retrieval_top_k,
        )
    except Exception as exc:
        logger.exception("Retrieval failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retrieval failed: {exc}",
        ) from exc

    assert session_id is not None  # both branches above assign it
    resolved_session_id: uuid.UUID = session_id

    async def event_source() -> AsyncIterator[dict[str, str]]:
        """Stream citations first, then tokens, then done. Errors short-circuit."""
        assistant_buffer: list[str] = []
        try:
            # Citations first — the frontend can render Sources immediately.
            for chunk in excerpts:
                yield _sse(
                    "citation",
                    {
                        "document_id": chunk.document_id,
                        "chunk_id": chunk.chunk_id,
                        "page": chunk.page,
                    },
                )

            # Tokens.
            async for token in _stream_claude(
                settings=settings,
                user_message=body.message,
                excerpts=excerpts,
            ):
                if await request.is_disconnected():
                    logger.info("Client disconnected mid-stream; aborting.")
                    break
                assistant_buffer.append(token)
                yield _sse("token", {"text": token})

            yield _sse("done", {"session_id": str(resolved_session_id)})
        except Exception as exc:
            logger.exception("Chat stream failed")
            yield _sse("error", {"message": str(exc)})
        finally:
            # Persist whatever we streamed, even on partial disconnect, so the
            # session history is truthful. Citations get denormalised alongside.
            if assistant_buffer:
                db.add(
                    ChatMessage(
                        session_id=resolved_session_id,
                        role="assistant",
                        content="".join(assistant_buffer),
                        citations=[
                            {
                                "document_id": c.document_id,
                                "chunk_id": c.chunk_id,
                                "page": c.page,
                            }
                            for c in excerpts
                        ],
                    )
                )
                await db.commit()

    return EventSourceResponse(event_source())
