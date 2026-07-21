"""Public (no-auth) demo endpoints.

Exposes the seeded "Northshore Medical Center" project to anonymous visitors so
the marketing site can offer a "See a live demo" experience without a Clerk
login. Everything here is READ-ONLY (plus a stateless RAG chat turn) and scoped
to a single hard-resolved demo project, so there's no tenant-isolation concern.

Deliberately NO auth dependency: these routes are meant to be hit anonymously.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from pmx_api.config import Settings, get_settings
from pmx_api.db.models import Document, HealthSnapshot, Project, Risk
from pmx_api.deps import DBSession
from pmx_api.pipeline.retrieve import retrieve_top_k

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/demo", tags=["demo"])

# Reuse the same grounding contract as the authed chat router so the demo answers
# behave identically (cite every claim, refuse when the excerpts don't cover it).
SYSTEM_PROMPT = (
    "You are a construction project management copilot. Answer using ONLY the "
    "provided document excerpts. Cite the page number for every claim in the "
    "form (p.N). If the answer isn't in the excerpts, say so. Be concise and "
    "speak like a seasoned project controls lead."
)


# --------------------------------------------------------------------------- #
# Demo project resolution                                                     #
# --------------------------------------------------------------------------- #


async def _resolve_demo_project(db: DBSession) -> Project | None:
    """Find the seeded demo project: name starts with 'Northshore' OR metadata demo=true."""
    result = await db.execute(
        select(Project)
        .where(
            or_(
                Project.name.ilike("Northshore%"),
                Project.metadata_["demo"].astext == "true",
            )
        )
        .order_by(Project.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# --------------------------------------------------------------------------- #
# GET /v1/demo/bundle                                                         #
# --------------------------------------------------------------------------- #


@router.get("/bundle", summary="Everything the public demo page renders, in one call")
async def demo_bundle(db: DBSession) -> dict:
    project = await _resolve_demo_project(db)
    if project is None:
        return {"project": None, "health": None, "risks": [], "documents": []}

    # Latest health snapshot for the project.
    snapshot = (
        await db.execute(
            select(HealthSnapshot)
            .where(HealthSnapshot.project_id == project.id)
            .order_by(HealthSnapshot.computed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    health: dict | None = None
    if snapshot is not None:
        factors: list[dict] = []
        raw = snapshot.factors or {}
        if isinstance(raw, dict):
            for key, v in raw.items():
                v = v if isinstance(v, dict) else {}
                sub_score = v.get("sub_score")
                score = round(sub_score * 100) if isinstance(sub_score, (int, float)) else 0
                factors.append(
                    {
                        "key": key,
                        "label": v.get("label") or key.replace("_", " ").title(),
                        "weight": v.get("weight", 0),
                        "score": score,
                    }
                )
        health = {"score": snapshot.score, "factors": factors}

    # Risks, severity desc.
    risk_rows = (
        await db.execute(
            select(Risk)
            .where(Risk.project_id == project.id)
            .order_by(Risk.severity.desc())
        )
    ).scalars().all()

    risks = [
        {
            "id": str(r.id),
            "category": r.category,
            "title": r.title,
            "description": r.description,
            "severity": r.severity,
            "likelihood": float(r.likelihood) if r.likelihood is not None else None,
            "confidence": float(r.confidence) if r.confidence is not None else None,
            "status": r.status,
            "business_impact": r.business_impact,
            "recommended_action": r.recommended_action,
            "citations": r.citations or [],
        }
        for r in risk_rows
    ]

    # Documents.
    doc_rows = (
        await db.execute(
            select(Document)
            .where(Document.project_id == project.id)
            .order_by(Document.uploaded_at.asc())
        )
    ).scalars().all()

    documents = [
        {
            "id": str(d.id),
            "filename": d.filename,
            "kind": d.kind,
            "status": d.status,
        }
        for d in doc_rows
    ]

    return {
        "project": {
            "name": project.name,
            "client": project.client,
            "sector": project.sector,
            "health_score": project.health_score,
            "planned_end_date": project.planned_end_date.isoformat()
            if project.planned_end_date
            else None,
            "forecast_end_date": project.forecast_end_date.isoformat()
            if project.forecast_end_date
            else None,
            "budget_total_cents": project.budget_total_cents,
            "budget_spent_cents": project.budget_spent_cents,
        },
        "health": health,
        "risks": risks,
        "documents": documents,
    }


# --------------------------------------------------------------------------- #
# POST /v1/demo/chat                                                          #
# --------------------------------------------------------------------------- #


class DemoChatRequest(BaseModel):
    message: str = Field(min_length=1)


async def _embed_query(query: str, settings: Settings) -> list[float]:
    """Embed the message with OpenAI (mirrors the authed chat router)."""
    from openai import OpenAI

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set; cannot embed query.")
    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.embeddings.create(model=settings.embedding_model, input=[query])
    return list(resp.data[0].embedding)


@router.post("/chat", summary="Stateless grounded chat over the demo project")
async def demo_chat(
    body: DemoChatRequest,
    db: DBSession,
    settings=Depends(get_settings),
) -> dict:
    project = await _resolve_demo_project(db)
    if project is None:
        return {
            "answer": "The demo project isn't seeded yet. Please check back shortly.",
            "citations": [],
        }

    try:
        embedding = await _embed_query(body.message, settings)
        excerpts = await retrieve_top_k(
            db,
            project_id=project.id,
            query_embedding=embedding,
            top_k=8,
        )
    except Exception:
        logger.exception("Demo retrieval failed")
        return {
            "answer": (
                "I couldn't reach the retrieval service just now. Try again in a "
                "moment, or ask about the project's schedule slip, budget "
                "variance, or overdue RFIs."
            ),
            "citations": [],
        }

    excerpt_block = (
        "\n\n".join(
            f"[chunk {i + 1}, p.{c.page}] {c.text}" for i, c in enumerate(excerpts)
        )
        or "(no relevant excerpts found)"
    )
    prompt = (
        "Document excerpts follow. Answer the question using only these.\n\n"
        f"{excerpt_block}\n\n"
        f"Question: {body.message}"
    )

    try:
        from anthropic import AsyncAnthropic

        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set; cannot answer chat.")
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        resp = await client.messages.create(
            model=settings.chat_model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        ).strip()
        if not answer:
            answer = "I don't have enough in the documents to answer that."
    except Exception:
        logger.exception("Demo chat generation failed")
        return {
            "answer": (
                "The AI assistant is temporarily unavailable. The seeded project "
                "shows an 11-week schedule slip and a 10.4% budget overrun, with "
                "8 open risks. Try again shortly for a cited answer."
            ),
            "citations": [
                {"document_id": c.document_id, "chunk_id": c.chunk_id, "page": c.page}
                for c in excerpts
            ],
        }

    return {
        "answer": answer,
        "citations": [
            {"document_id": c.document_id, "chunk_id": c.chunk_id, "page": c.page}
            for c in excerpts
        ],
    }
