"""Meeting Intelligence router — transcript → summary + actions + decisions.

M3 scope. The endpoint accepts either:

* JSON body ``{transcript_text, meeting_date?}`` — for pasted transcripts,
  and the browser textarea path.
* Multipart ``file`` upload (.txt / .docx / .pdf) — for dropped files.

We route on ``Content-Type`` at the top of the handler so the client only
ever sees one URL. Extraction is inline (small documents, single-request
latency budget), matching the M1 documents router pattern.

The LLM pass calls Claude Sonnet 4.6 with a strict ``emit_meeting_analysis``
tool so the response is always structured JSON. Missing ``ANTHROPIC_API_KEY``
returns a 503 rather than crashing — this endpoint is opt-in intelligence,
not a hard dependency.

If the LLM surfaces ``risks_surfaced`` we optionally insert rows into
``risks`` with a ``rule_key = f"meeting:{meeting_id}:{i}"`` so subsequent
uploads of the same transcript don't stack duplicates.
"""

from __future__ import annotations

import io
import logging
import uuid
from datetime import date
from typing import Annotated, Any, cast

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import select

from pmx_api.config import Settings, get_settings
from pmx_api.db.models import Meeting, Project, Risk
from pmx_api.deps import (
    CurrentUser,
    DBSession,
    TenantContext,
    require_current_user,
    resolve_tenant,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Router configuration                                                        #
# --------------------------------------------------------------------------- #

# Two prefixes so the URL shape mirrors DESIGN §5 ("project-scoped for
# ownership; identity-scoped for detail"). Mirrors the ``risks`` router.
project_scoped_router = APIRouter(
    prefix="/v1/projects/{project_id}/meetings",
    tags=["meetings"],
)
meeting_scoped_router = APIRouter(prefix="/v1/meetings", tags=["meetings"])


# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #

VALID_RISK_CATEGORIES = (
    "schedule",
    "budget",
    "operational",
    "communication",
    "compliance",
)

# Cap transcript size so a runaway upload can't blow through the context
# budget or the multipart parser's memory. 500 kB of raw transcript is
# ~100k words — well past any real meeting.
MAX_TRANSCRIPT_BYTES = 500_000

LLM_SYSTEM_PROMPT = (
    "You are a senior construction project manager reviewing a meeting "
    "transcript. Extract: (1) a concise 2-3 paragraph executive summary, "
    "(2) explicit action items with owner and due date if stated, "
    "(3) decisions made and who made them, and (4) any risks surfaced "
    "that a PM should act on. Only include content actually present in "
    "the transcript — never invent owners, dates, or decisions. Use the "
    "``emit_meeting_analysis`` tool to return your findings."
)

LLM_ANALYSIS_TOOL: dict[str, Any] = {
    "name": "emit_meeting_analysis",
    "description": (
        "Emit the structured meeting analysis: summary, action items, "
        "decisions, and any risks surfaced during the meeting."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": (
                    "Executive summary of the meeting, 2-3 paragraphs. "
                    "Written for a busy PM skimming the day's meetings."
                ),
            },
            "action_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "What needs to be done.",
                        },
                        "owner": {
                            "type": "string",
                            "description": (
                                "Person / role responsible. Empty string "
                                "if not explicitly assigned in transcript."
                            ),
                        },
                        "due_date": {
                            "type": "string",
                            "description": (
                                "Due date in ISO 8601 (YYYY-MM-DD) if the "
                                "transcript names one; empty string otherwise."
                            ),
                        },
                    },
                    "required": ["text", "owner", "due_date"],
                },
            },
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "What was decided.",
                        },
                        "made_by": {
                            "type": "string",
                            "description": (
                                "Person / role who made the decision; empty string if unclear."
                            ),
                        },
                    },
                    "required": ["text", "made_by"],
                },
            },
            "risks_surfaced": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The risk as raised in the meeting.",
                        },
                        "category": {
                            "type": "string",
                            "enum": list(VALID_RISK_CATEGORIES),
                        },
                        "severity_1_to_5": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 5,
                            "description": ("1 = minor, 5 = project-threatening."),
                        },
                    },
                    "required": ["text", "category", "severity_1_to_5"],
                },
            },
        },
        "required": ["summary", "action_items", "decisions", "risks_surfaced"],
    },
}


# --------------------------------------------------------------------------- #
# Schemas                                                                     #
# --------------------------------------------------------------------------- #


class ActionItem(BaseModel):
    text: str
    owner: str = ""
    due_date: str = ""
    done: bool = False


class Decision(BaseModel):
    text: str
    made_by: str = ""


class SurfacedRisk(BaseModel):
    text: str
    category: str
    severity_1_to_5: int = Field(ge=1, le=5)


class MeetingAnalysis(BaseModel):
    """The LLM's structured output; also the shape we persist to Meeting."""

    summary: str
    action_items: list[ActionItem]
    decisions: list[Decision]
    risks_surfaced: list[SurfacedRisk]


class AnalyzeRequest(BaseModel):
    """JSON body variant of the analyze endpoint."""

    transcript_text: str
    meeting_date: date | None = None


class AnalyzeResponse(BaseModel):
    meeting_id: str
    summary: str
    action_items: list[ActionItem]
    decisions: list[Decision]
    risks_created: int


class MeetingSummary(BaseModel):
    """Row shape for the list view."""

    id: str
    project_id: str
    meeting_date: date | None
    summary: str | None
    action_item_count: int
    decision_count: int


class MeetingDetail(BaseModel):
    """Full detail — decisions + action items as structured objects."""

    id: str
    project_id: str
    meeting_date: date | None
    summary: str | None
    action_items: list[ActionItem]
    decisions: list[Decision]


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


async def _load_project_scoped(
    db: DBSession, project_id: uuid.UUID, tenant: TenantContext
) -> Project:
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
    return project


async def _load_meeting_scoped(
    db: DBSession, meeting_id: uuid.UUID, tenant: TenantContext
) -> Meeting:
    row = (
        await db.execute(
            select(Meeting, Project)
            .join(Project, Project.id == Meeting.project_id)
            .where(
                Meeting.id == meeting_id,
                Project.org_id == uuid.UUID(tenant.org_uuid),
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found",
        )
    meeting: Meeting = row[0]
    return meeting


def _extract_txt(raw: bytes) -> str:
    """UTF-8 decode with a lenient fallback so Windows exports don't 500."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def _extract_docx(raw: bytes) -> str:
    """Pull paragraph text from a DOCX blob via python-docx."""
    from docx import Document as DocxDocument

    doc = DocxDocument(io.BytesIO(raw))
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_pdf(raw: bytes) -> str:
    """Pull page text from a PDF via PyMuPDF."""
    import fitz  # PyMuPDF

    pieces: list[str] = []
    with fitz.open(stream=raw, filetype="pdf") as pdf:
        for i in range(pdf.page_count):
            page = pdf.load_page(i)
            pieces.append(cast(str, page.get_text("text")))
    return "\n\n".join(p for p in pieces if p.strip())


def _extract_from_upload(file: UploadFile, raw: bytes) -> str:
    """Route the upload to the right extractor based on filename + MIME.

    We prefer filename extension because browsers frequently send
    ``application/octet-stream`` for .docx and .txt drops.
    """
    name = (file.filename or "").lower()
    ctype = (file.content_type or "").lower()

    if name.endswith(".txt") or ctype.startswith("text/"):
        return _extract_txt(raw)
    if name.endswith(".docx") or "wordprocessingml" in ctype:
        return _extract_docx(raw)
    if name.endswith(".pdf") or ctype == "application/pdf":
        return _extract_pdf(raw)

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=(
            "Unsupported file type. Upload .txt, .docx, or .pdf "
            f"(got filename={file.filename!r}, content_type={file.content_type!r})."
        ),
    )


# --------------------------------------------------------------------------- #
# LLM pass                                                                    #
# --------------------------------------------------------------------------- #


async def _call_llm_analyze(
    *,
    settings: Settings,
    transcript: str,
    meeting_date: date | None,
) -> MeetingAnalysis:
    """Ask Claude for a structured meeting analysis.

    Missing key → 503 (surfaced by the caller). Malformed tool response → we
    parse defensively and return whatever the LLM did send, dropping bad
    entries. If the LLM never called the tool, we return an empty analysis
    with just the raw text as summary so the endpoint still succeeds.
    """
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Meeting Intelligence needs ANTHROPIC_API_KEY set on the API. "
                "Ask your admin to configure it, then retry."
            ),
        )

    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    date_hint = (
        f"Meeting date (as tagged on upload): {meeting_date.isoformat()}\n\n"
        if meeting_date is not None
        else ""
    )
    user_prompt = (
        f"{date_hint}"
        "Transcript follows between the fenced markers.\n"
        "```\n"
        f"{transcript}\n"
        "```\n\n"
        "Extract the structured meeting analysis. Call the "
        "``emit_meeting_analysis`` tool exactly once."
    )

    try:
        response = await client.messages.create(
            model=settings.chat_model,
            max_tokens=4096,
            system=LLM_SYSTEM_PROMPT,
            tools=cast(Any, [LLM_ANALYSIS_TOOL]),
            tool_choice=cast(Any, {"type": "tool", "name": "emit_meeting_analysis"}),
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as exc:
        logger.warning("Claude meeting-analysis call failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM call failed: {exc}",
        ) from exc

    return _parse_llm_response(response)


def _parse_llm_response(response: Any) -> MeetingAnalysis:
    """Extract the ``emit_meeting_analysis`` tool payload defensively.

    Same shape-tolerance approach as risks._parse_llm_response — handles
    both attribute-style blocks (real SDK) and dict-style (test fakes).
    """
    for block in getattr(response, "content", []):
        block_type = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None
        )
        if block_type != "tool_use":
            continue
        payload = getattr(block, "input", None) or (
            block.get("input") if isinstance(block, dict) else None
        )
        if not isinstance(payload, dict):
            continue
        return _payload_to_analysis(payload)

    # No tool call — degrade to an empty analysis rather than 500.
    logger.info("Claude did not call emit_meeting_analysis; returning empty analysis.")
    return MeetingAnalysis(
        summary="(No structured analysis returned.)",
        action_items=[],
        decisions=[],
        risks_surfaced=[],
    )


def _payload_to_analysis(payload: dict[str, Any]) -> MeetingAnalysis:
    """Coerce the raw tool input into a validated ``MeetingAnalysis``.

    We're generous: missing keys default to safe empties, malformed rows
    are dropped with a warning. A single bad field never fails the whole
    analysis.
    """
    summary = str(payload.get("summary") or "")

    action_items: list[ActionItem] = []
    for raw in payload.get("action_items") or []:
        if not isinstance(raw, dict):
            continue
        try:
            action_items.append(
                ActionItem(
                    text=str(raw.get("text") or ""),
                    owner=str(raw.get("owner") or ""),
                    due_date=str(raw.get("due_date") or ""),
                    done=False,
                )
            )
        except (TypeError, ValueError) as exc:
            logger.warning("Dropping malformed action item %s: %s", raw, exc)

    decisions: list[Decision] = []
    for raw in payload.get("decisions") or []:
        if not isinstance(raw, dict):
            continue
        try:
            decisions.append(
                Decision(
                    text=str(raw.get("text") or ""),
                    made_by=str(raw.get("made_by") or ""),
                )
            )
        except (TypeError, ValueError) as exc:
            logger.warning("Dropping malformed decision %s: %s", raw, exc)

    risks_surfaced: list[SurfacedRisk] = []
    for raw in payload.get("risks_surfaced") or []:
        if not isinstance(raw, dict):
            continue
        try:
            severity = int(raw.get("severity_1_to_5") or 3)
            severity = max(1, min(5, severity))
            category = str(raw.get("category") or "operational")
            if category not in VALID_RISK_CATEGORIES:
                category = "operational"
            risks_surfaced.append(
                SurfacedRisk(
                    text=str(raw.get("text") or ""),
                    category=category,
                    severity_1_to_5=severity,
                )
            )
        except (TypeError, ValueError) as exc:
            logger.warning("Dropping malformed surfaced risk %s: %s", raw, exc)

    return MeetingAnalysis(
        summary=summary,
        action_items=action_items,
        decisions=decisions,
        risks_surfaced=risks_surfaced,
    )


# --------------------------------------------------------------------------- #
# Persistence                                                                 #
# --------------------------------------------------------------------------- #


def _action_items_to_json(items: list[ActionItem]) -> list[dict[str, object]]:
    """Coerce ActionItem models to JSONB-ready dicts.

    ``model_dump`` returns ``dict[str, Any]`` and JSONB wants ``dict[str,
    object]``; we build the dict explicitly so mypy strict stays green.
    """
    return [
        {
            "text": item.text,
            "owner": item.owner,
            "due_date": item.due_date,
            "done": item.done,
        }
        for item in items
    ]


def _decisions_to_json(items: list[Decision]) -> list[dict[str, object]]:
    return [{"text": item.text, "made_by": item.made_by} for item in items]


async def _persist_meeting(
    *,
    db: DBSession,
    project_id: uuid.UUID,
    analysis: MeetingAnalysis,
    meeting_date: date | None,
) -> Meeting:
    meeting = Meeting(
        project_id=project_id,
        meeting_date=meeting_date,
        summary=analysis.summary,
        decisions=_decisions_to_json(analysis.decisions),
        action_items=_action_items_to_json(analysis.action_items),
    )
    db.add(meeting)
    await db.flush()
    return meeting


async def _create_risks_from_surfaced(
    *,
    db: DBSession,
    project_id: uuid.UUID,
    meeting_id: uuid.UUID,
    risks_surfaced: list[SurfacedRisk],
) -> int:
    """Create one ``risks`` row per surfaced risk. Returns the number created.

    We use ``rule_key = f"meeting:{meeting_id}:{i}"`` so re-running an
    analyze on the same transcript (which produces a new meeting_id) still
    creates fresh rows — this is intentional; every analysis is a snapshot.
    """
    created = 0
    for i, r in enumerate(risks_surfaced):
        if not r.text:
            continue
        metadata: dict[str, object] = {
            "rule_key": f"meeting:{meeting_id}:{i}",
            "source": "meeting",
            "meeting_id": str(meeting_id),
        }
        risk = Risk(
            project_id=project_id,
            category=r.category,
            title=f"Meeting-raised risk: {r.text[:80]}",
            description=r.text,
            severity=r.severity_1_to_5,
            likelihood=0.7,
            business_impact="Raised during project meeting; verify with PM.",
            recommended_action="Discuss at next stand-up and assign an owner.",
            confidence=0.6,
            citations=None,
            metadata_=metadata,
        )
        db.add(risk)
        created += 1
    return created


# --------------------------------------------------------------------------- #
# Routes                                                                      #
# --------------------------------------------------------------------------- #


@project_scoped_router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="Analyze a meeting transcript (JSON body or multipart file).",
)
async def analyze_meeting(
    project_id: uuid.UUID,
    request: Request,
    db: DBSession,
    current: Annotated[CurrentUser, Depends(require_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AnalyzeResponse:
    tenant = await resolve_tenant(db, current)
    project = await _load_project_scoped(db, project_id, tenant)

    transcript, meeting_date = await _read_transcript(request)
    if not transcript.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transcript is empty. Paste text or upload a file with content.",
        )
    if len(transcript.encode("utf-8")) > MAX_TRANSCRIPT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Transcript exceeds {MAX_TRANSCRIPT_BYTES // 1000} kB. "
                "Trim or split the transcript before re-uploading."
            ),
        )

    analysis = await _call_llm_analyze(
        settings=settings,
        transcript=transcript,
        meeting_date=meeting_date,
    )

    meeting = await _persist_meeting(
        db=db,
        project_id=project.id,
        analysis=analysis,
        meeting_date=meeting_date,
    )

    risks_created = await _create_risks_from_surfaced(
        db=db,
        project_id=project.id,
        meeting_id=meeting.id,
        risks_surfaced=analysis.risks_surfaced,
    )

    await db.commit()
    await db.refresh(meeting)

    return AnalyzeResponse(
        meeting_id=str(meeting.id),
        summary=analysis.summary,
        action_items=analysis.action_items,
        decisions=analysis.decisions,
        risks_created=risks_created,
    )


async def _read_transcript(request: Request) -> tuple[str, date | None]:
    """Pull transcript + optional date out of either a JSON body or multipart form.

    Split out from the handler so the two input paths stay readable and the
    handler focuses on the analyze pipeline.
    """
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()

    if ctype == "application/json":
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON body: {exc}",
            ) from exc
        try:
            parsed = AnalyzeRequest.model_validate(body)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid analyze payload: {exc}",
            ) from exc
        return parsed.transcript_text, parsed.meeting_date

    if ctype == "multipart/form-data":
        form = await request.form()
        raw_file = form.get("file")
        if not isinstance(raw_file, UploadFile):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Multipart request must include a ``file`` field.",
            )
        contents = await raw_file.read()
        if len(contents) > MAX_TRANSCRIPT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"File exceeds {MAX_TRANSCRIPT_BYTES // 1000} kB. "
                    "Trim or split before uploading."
                ),
            )
        transcript = _extract_from_upload(raw_file, contents)

        # Optional meeting_date form field.
        meeting_date_raw = form.get("meeting_date")
        meeting_date: date | None = None
        if isinstance(meeting_date_raw, str) and meeting_date_raw.strip():
            try:
                meeting_date = date.fromisoformat(meeting_date_raw.strip())
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid meeting_date (want YYYY-MM-DD): {exc}",
                ) from exc

        return transcript, meeting_date

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=(
            "Send either application/json or multipart/form-data "
            f"(got {ctype or 'no content-type'})."
        ),
    )


@project_scoped_router.get(
    "",
    response_model=list[MeetingSummary],
    summary="List meetings for a project.",
)
async def list_meetings(
    project_id: uuid.UUID,
    db: DBSession,
    current: Annotated[CurrentUser, Depends(require_current_user)],
) -> list[MeetingSummary]:
    tenant = await resolve_tenant(db, current)
    await _load_project_scoped(db, project_id, tenant)

    stmt = (
        select(Meeting)
        .where(Meeting.project_id == project_id)
        .order_by(Meeting.meeting_date.desc().nulls_last(), Meeting.id.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()

    def _count(v: object) -> int:
        return len(v) if isinstance(v, list) else 0

    return [
        MeetingSummary(
            id=str(m.id),
            project_id=str(m.project_id),
            meeting_date=m.meeting_date,
            summary=(m.summary[:280] if m.summary else None),
            action_item_count=_count(m.action_items),
            decision_count=_count(m.decisions),
        )
        for m in rows
    ]


@meeting_scoped_router.get(
    "/{meeting_id}",
    response_model=MeetingDetail,
    summary="Get a meeting's structured analysis.",
)
async def get_meeting(
    meeting_id: uuid.UUID,
    db: DBSession,
    current: Annotated[CurrentUser, Depends(require_current_user)],
) -> MeetingDetail:
    tenant = await resolve_tenant(db, current)
    meeting = await _load_meeting_scoped(db, meeting_id, tenant)

    raw_actions = meeting.action_items or []
    raw_decisions = meeting.decisions or []

    actions: list[ActionItem] = []
    for raw in raw_actions:
        if isinstance(raw, dict):
            actions.append(
                ActionItem(
                    text=str(raw.get("text") or ""),
                    owner=str(raw.get("owner") or ""),
                    due_date=str(raw.get("due_date") or ""),
                    done=bool(raw.get("done") or False),
                )
            )

    decisions: list[Decision] = []
    for raw in raw_decisions:
        if isinstance(raw, dict):
            decisions.append(
                Decision(
                    text=str(raw.get("text") or ""),
                    made_by=str(raw.get("made_by") or ""),
                )
            )

    return MeetingDetail(
        id=str(meeting.id),
        project_id=str(meeting.project_id),
        meeting_date=meeting.meeting_date,
        summary=meeting.summary,
        action_items=actions,
        decisions=decisions,
    )


__all__ = [
    "LLM_ANALYSIS_TOOL",
    "AnalyzeResponse",
    "MeetingAnalysis",
    "MeetingDetail",
    "MeetingSummary",
    "meeting_scoped_router",
    "project_scoped_router",
]
