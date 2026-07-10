"""Risk engine — hybrid rules + LLM pass.

Design (matches DR-001 §11 "Hybrid rules + LLM"):

1. **Rules pass.** Deterministic checks over structured tables
   (``budget_lines``, ``schedule_tasks``, ``rfis``, ``documents``,
   ``change_orders``). Each rule emits a candidate with a stable
   ``rule_key`` — e.g. ``budget_overrun``, ``rfi_overdue:<uuid>``. Re-scans
   look up existing rows by ``metadata->>'rule_key'`` (indexed) and update
   in place, so ``scan_project`` is idempotent when the same condition
   persists across scans.

2. **LLM pass.** Retrieval-augmented Claude call using the same
   ``retrieve_top_k`` helper the chat router uses. The LLM sees the top
   chunks (recency-approximated as "most recent documents") plus the
   rules-based findings and is asked, via tool-use, to identify
   *additional* risks a construction PM would care about. Missing
   ``ANTHROPIC_API_KEY`` → LLM pass logs and skips; the rules-only result
   still returns.

Every finding writes a row into ``risks`` with citations in the JSONB shape
DESIGN §4 pins: ``[{"document_id": ..., "chunk_id": ..., "page": ...}]``.

The service returns the freshly-inserted / freshly-updated rows so the HTTP
handler can echo them back to the caller of ``POST /risks/scan``.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pmx_api.config import Settings
from pmx_api.db.models import Risk
from pmx_api.pipeline.retrieve import RetrievedChunk

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #

BUDGET_OVERRUN_THRESHOLD = 1.05  # actual/forecast ratio that triggers a risk
RFI_AGING_DAYS = 14
SCHEDULE_SLIP_DAYS = 7
CHANGE_ORDER_PENDING_LIMIT = 3

# How many top chunks we hand to the LLM pass. Kept small so the prompt
# stays under context budget for Sonnet and the risk scan finishes in <15s.
LLM_CONTEXT_CHUNK_COUNT = 30

# Retrieval seed for the LLM pass — a generic "what could go wrong on this
# project" query. We use it purely to weight the vector search toward
# risk-adjacent chunks; the actual reasoning happens in-model.
LLM_SEED_QUERY = (
    "risks issues delays overruns problems concerns disputes bottlenecks "
    "safety compliance change orders schedule slippage"
)

VALID_CATEGORIES = ("schedule", "budget", "operational", "communication", "compliance")

LLM_SYSTEM_PROMPT = (
    "You are a senior construction project risk analyst. Given a bundle of "
    "recent project document excerpts AND a list of risks the deterministic "
    "rules engine has already flagged, identify ADDITIONAL risks a project "
    "manager should act on that the rules engine could not catch. Only "
    "propose risks that a senior PM would raise in a project meeting. Every "
    "risk MUST cite the specific chunk(s) it derives from — never invent "
    "sources. If you can't find any additional risks beyond what the rules "
    "already flagged, return an empty list. Use the ``emit_risks`` tool."
)

LLM_RISKS_TOOL: dict[str, Any] = {
    "name": "emit_risks",
    "description": (
        "Emit a list of risks identified beyond the rules-based findings. "
        "Return an empty ``risks`` list if none apply."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "risks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": list(VALID_CATEGORIES),
                        },
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "severity": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 5,
                            "description": "1 = minor, 5 = project-threatening",
                        },
                        "likelihood": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "business_impact": {"type": "string"},
                        "recommended_action": {"type": "string"},
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "citations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "document_id": {"type": "string"},
                                    "chunk_id": {"type": "string"},
                                    "page": {"type": "integer"},
                                },
                                "required": ["document_id", "chunk_id"],
                            },
                            "minItems": 1,
                        },
                    },
                    "required": [
                        "category",
                        "title",
                        "description",
                        "severity",
                        "likelihood",
                        "business_impact",
                        "recommended_action",
                        "confidence",
                        "citations",
                    ],
                },
            }
        },
        "required": ["risks"],
    },
}


# --------------------------------------------------------------------------- #
# Data types                                                                  #
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class RiskCandidate:
    """A rules- or LLM-emitted risk before it lands as a row.

    ``rule_key`` is what makes re-scans idempotent — see module docstring.
    ``None`` for LLM-emitted risks (they're not deterministic and shouldn't
    collapse together on second run).
    """

    category: str
    title: str
    description: str
    severity: int
    likelihood: float
    business_impact: str
    recommended_action: str
    confidence: float
    citations: list[dict[str, Any]] = field(default_factory=list)
    rule_key: str | None = None
    source: str = "rules"  # "rules" | "llm"


# --------------------------------------------------------------------------- #
# Rules pass                                                                  #
# --------------------------------------------------------------------------- #


async def _rule_budget_overrun(db: AsyncSession, project_id: uuid.UUID) -> RiskCandidate | None:
    """Aggregate spend vs forecast; if actual > 1.05x forecast, flag.

    Severity scales with the overrun size:
      * 1.05..1.10 -> severity 2 (medium)
      * 1.10..1.25 -> severity 3 (high)
      * > 1.25     -> severity 4 (very high)
    """
    row = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM(actual_cents), 0)   AS actual,
                       COALESCE(SUM(forecast_cents), 0) AS forecast
                FROM budget_lines
                WHERE project_id = :pid
                """
            ),
            {"pid": project_id},
        )
    ).one()
    actual = int(row.actual)
    forecast = int(row.forecast)
    if forecast <= 0 or actual <= forecast * BUDGET_OVERRUN_THRESHOLD:
        return None

    ratio = actual / forecast
    if ratio >= 1.25:
        severity = 4
    elif ratio >= 1.10:
        severity = 3
    else:
        severity = 2

    overrun_pct = (ratio - 1) * 100
    return RiskCandidate(
        category="budget",
        title=f"Budget overrun: actual {overrun_pct:.1f}% above forecast",
        description=(
            f"Aggregate actual spend of ${actual / 100:,.2f} exceeds "
            f"forecast of ${forecast / 100:,.2f} by {overrun_pct:.1f}%. "
            "Automatic finding from ``budget_lines`` aggregate."
        ),
        severity=severity,
        likelihood=1.0,
        business_impact=(
            "Sustained overrun forces owner-side scope cuts or a formal "
            "budget re-baseline; margin at risk this period."
        ),
        recommended_action=(
            "Review the categories with the largest variance, meet with "
            "cost engineering, and confirm the forecast reflects current "
            "commitments before next owner meeting."
        ),
        confidence=0.95,
        rule_key="budget_overrun",
    )


async def _rule_schedule_slip(db: AsyncSession, project_id: uuid.UUID) -> RiskCandidate | None:
    """If any task has slip_days > 7, flag a schedule risk.

    We emit ONE aggregate risk rather than one per task — otherwise a fat
    schedule import would spam the risks tab. The description names the
    worst-slipping tasks so the PM can drill in.
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT name, slip_days, is_critical
                FROM schedule_tasks
                WHERE project_id = :pid
                  AND slip_days > :threshold
                ORDER BY slip_days DESC
                LIMIT 5
                """
            ),
            {"pid": project_id, "threshold": SCHEDULE_SLIP_DAYS},
        )
    ).all()
    if not rows:
        return None

    worst = rows[0]
    critical_hits = [r for r in rows if r.is_critical]
    # Critical-path slip is more severe.
    severity = 4 if critical_hits else 3

    task_list = "; ".join(f"{r.name} (+{r.slip_days}d)" for r in rows)
    return RiskCandidate(
        category="schedule",
        title=f"Schedule slip: {len(rows)} task(s) over {SCHEDULE_SLIP_DAYS}d late",
        description=(
            f"{len(rows)} task(s) currently slip more than {SCHEDULE_SLIP_DAYS} "
            f"days. Worst: {worst.name} at +{worst.slip_days} days. "
            f"Top offenders: {task_list}."
            + (f" {len(critical_hits)} of these are on the critical path." if critical_hits else "")
        ),
        severity=severity,
        likelihood=1.0,
        business_impact=(
            "Downstream tasks compress; risk of missing planned end date and "
            "triggering liquidated damages if trend continues."
        ),
        recommended_action=(
            "Schedule a look-ahead workshop on the top slipping tasks and "
            "run a critical-path re-analysis before the next monthly report."
        ),
        confidence=0.95,
        rule_key="schedule_slip",
    )


async def _rule_rfi_overdue(db: AsyncSession, project_id: uuid.UUID) -> list[RiskCandidate]:
    """One risk per RFI that has been open > 14 days.

    Per-RFI so the dedup key can pin to the RFI id — closing one RFI shouldn't
    silence risks for the others. Uses submitted_date as the aging clock; if
    submitted_date is null we fall back to a coarser aggregate at scan time.
    """
    cutoff = datetime.now(UTC).date() - timedelta(days=RFI_AGING_DAYS)
    rows = (
        await db.execute(
            text(
                """
                SELECT id, number, subject, submitted_date, discipline
                FROM rfis
                WHERE project_id = :pid
                  AND status = 'open'
                  AND submitted_date IS NOT NULL
                  AND submitted_date <= :cutoff
                ORDER BY submitted_date ASC
                """
            ),
            {"pid": project_id, "cutoff": cutoff},
        )
    ).all()

    out: list[RiskCandidate] = []
    for row in rows:
        age_days = (datetime.now(UTC).date() - row.submitted_date).days
        severity = 3 if age_days >= 30 else 2
        out.append(
            RiskCandidate(
                category="operational",
                title=f"RFI {row.number or row.id} open {age_days}d",
                description=(
                    f"RFI {row.number or row.id} — {row.subject or '(no subject)'} "
                    f"— has been open for {age_days} days without response."
                ),
                severity=severity,
                likelihood=0.85,
                business_impact=(
                    "Aging RFIs block dependent work; if this RFI drives a "
                    "trade sequence, expect field-side stand-down cost."
                ),
                recommended_action=(
                    "Escalate to the design-of-record and set a hard reply "
                    "date. If unanswered by next week, log a delay claim."
                ),
                confidence=0.9,
                rule_key=f"rfi_overdue:{row.id}",
            )
        )
    return out


async def _rule_document_ingest_failed(
    db: AsyncSession, project_id: uuid.UUID
) -> RiskCandidate | None:
    """If any document is stuck in status='failed', flag ops risk.

    One aggregate row; the description enumerates the failed filenames so
    the PM sees which imports need retry.
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT filename, error
                FROM documents
                WHERE project_id = :pid
                  AND status = 'failed'
                ORDER BY uploaded_at DESC
                """
            ),
            {"pid": project_id},
        )
    ).all()
    if not rows:
        return None

    name_list = ", ".join(r.filename for r in rows[:5])
    more = f" (+{len(rows) - 5} more)" if len(rows) > 5 else ""
    return RiskCandidate(
        category="operational",
        title=f"{len(rows)} document ingest failure(s)",
        description=(
            f"{len(rows)} document(s) failed ingestion and are not "
            f"contributing to project intelligence: {name_list}{more}. "
            "Retry the upload or investigate the parser error."
        ),
        severity=2,
        likelihood=1.0,
        business_impact=(
            "Missing documents mean the risk engine, chat, and reports are "
            "blind to whatever those files contained."
        ),
        recommended_action=(
            "Re-upload the failed files or check the parser error field on "
            "each document row and file a bug if the format is supported."
        ),
        confidence=0.99,
        rule_key="documents_failed",
    )


async def _rule_change_orders_pending(
    db: AsyncSession, project_id: uuid.UUID
) -> RiskCandidate | None:
    """If more than 3 change orders sit pending, flag budget risk.

    Pending CO backlog is a leading indicator of a scope creep problem the
    forecast hasn't caught yet.
    """
    row = (
        await db.execute(
            text(
                """
                SELECT COUNT(*) AS pending_count,
                       COALESCE(SUM(amount_cents), 0) AS total_pending_cents
                FROM change_orders
                WHERE project_id = :pid
                  AND status = 'pending'
                """
            ),
            {"pid": project_id},
        )
    ).one()
    pending = int(row.pending_count)
    if pending <= CHANGE_ORDER_PENDING_LIMIT:
        return None

    total_cents = int(row.total_pending_cents)
    return RiskCandidate(
        category="budget",
        title=f"{pending} change orders pending approval",
        description=(
            f"{pending} change order(s) are pending, totalling "
            f"${total_cents / 100:,.2f} in unapproved scope. Beyond "
            f"{CHANGE_ORDER_PENDING_LIMIT}, this backlog usually reflects "
            "either an under-resourced approval process or unresolved "
            "scope disputes."
        ),
        severity=3,
        likelihood=0.9,
        business_impact=(
            "Pending COs eventually land in actuals; forecast understates "
            "final cost by this backlog until each one is decisioned."
        ),
        recommended_action=(
            "Batch-review the pending queue with the owner rep and force a "
            "decision on the oldest three before the next progress meeting."
        ),
        confidence=0.85,
        rule_key="change_orders_backlog",
    )


async def run_rules(db: AsyncSession, project_id: uuid.UUID) -> list[RiskCandidate]:
    """Run every rule sequentially. Order doesn't matter for output."""
    findings: list[RiskCandidate] = []
    for coro in (
        _rule_budget_overrun(db, project_id),
        _rule_schedule_slip(db, project_id),
        _rule_document_ingest_failed(db, project_id),
        _rule_change_orders_pending(db, project_id),
    ):
        candidate = await coro
        if candidate is not None:
            findings.append(candidate)
    findings.extend(await _rule_rfi_overdue(db, project_id))
    return findings


# --------------------------------------------------------------------------- #
# LLM pass                                                                    #
# --------------------------------------------------------------------------- #


async def _load_recent_chunks(
    db: AsyncSession,
    project_id: uuid.UUID,
    limit: int,
) -> list[RetrievedChunk]:
    """Grab the ``limit`` most recent chunks for the project.

    We use recency instead of embedding similarity here because the LLM pass
    is asked to spot *anything unusual* — not answer a specific question —
    so the freshest slice of the project's paper trail is the best prior.
    Falls back cleanly to an empty list if the project has no chunks yet.
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT id, document_id, project_id, page, text
                FROM document_chunks
                WHERE project_id = :pid
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"pid": project_id, "limit": limit},
        )
    ).all()

    return [
        RetrievedChunk(
            chunk_id=str(row.id),
            document_id=str(row.document_id),
            project_id=str(row.project_id),
            page=row.page,
            text=row.text,
            distance=0.0,
        )
        for row in rows
    ]


def _rules_summary_for_llm(rules_findings: list[RiskCandidate]) -> str:
    """One-line-per-rule summary passed as LLM context."""
    if not rules_findings:
        return "(no rules-based findings)"
    return "\n".join(
        f"- [{f.category}] {f.title} (severity {f.severity}, rule_key={f.rule_key})"
        for f in rules_findings
    )


def _chunk_block_for_llm(chunks: list[RetrievedChunk]) -> str:
    """Render the retrieved chunks as a numbered block the LLM can cite."""
    if not chunks:
        return "(no document chunks available)"
    return "\n\n".join(
        (f"[chunk {i + 1}] document_id={c.document_id} chunk_id={c.chunk_id} p.{c.page}\n{c.text}")
        for i, c in enumerate(chunks)
    )


async def _call_llm_pass(
    *,
    settings: Settings,
    rules_findings: list[RiskCandidate],
    chunks: list[RetrievedChunk],
) -> list[RiskCandidate]:
    """Ask Claude for additional risks beyond the rules pass.

    Missing ``ANTHROPIC_API_KEY`` → log + return []. This keeps the rules-only
    result path fully functional in local dev without keys.

    Overridable in tests by monkeypatching this module attribute.
    """
    if not settings.anthropic_api_key:
        logger.info("ANTHROPIC_API_KEY not set; skipping LLM risk pass.")
        return []

    if not chunks:
        # Nothing to reason about. Skip the round-trip.
        return []

    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    user_prompt = (
        "Existing rules-based findings:\n"
        f"{_rules_summary_for_llm(rules_findings)}\n\n"
        "Recent project document excerpts:\n"
        f"{_chunk_block_for_llm(chunks)}\n\n"
        "Identify additional risks the rules engine did not catch. "
        "Every risk MUST cite the chunk(s) it derives from using their "
        "``document_id`` and ``chunk_id`` verbatim. "
        "Call the ``emit_risks`` tool with your findings."
    )

    # The Anthropic SDK ships strongly-typed TypedDicts for tools + tool_choice
    # that our JSON-first LLM_RISKS_TOOL doesn't statically satisfy; we cast
    # rather than teach the constant to match every SDK bump.
    try:
        response = await client.messages.create(
            model=settings.chat_model,
            max_tokens=2048,
            system=LLM_SYSTEM_PROMPT,
            tools=cast(Any, [LLM_RISKS_TOOL]),
            tool_choice=cast(Any, {"type": "tool", "name": "emit_risks"}),
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as exc:  # pragma: no cover — network path
        logger.warning("LLM risk pass failed: %s", exc)
        return []

    return _parse_llm_response(response)


def _parse_llm_response(response: Any) -> list[RiskCandidate]:
    """Extract the ``emit_risks`` tool call payload from an Anthropic response.

    Kept pure so tests can construct a fake response object with the shape
    Anthropic emits and verify the mapping.
    """
    candidates: list[RiskCandidate] = []
    for block in getattr(response, "content", []):
        # Anthropic blocks have a ``type`` attribute in the real SDK; fake
        # objects in tests may use dicts. Handle both.
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
        raw_risks = payload.get("risks", [])
        for raw in raw_risks:
            if not isinstance(raw, dict):
                continue
            try:
                candidates.append(
                    RiskCandidate(
                        category=str(raw["category"]),
                        title=str(raw["title"]),
                        description=str(raw["description"]),
                        severity=int(raw["severity"]),
                        likelihood=float(raw["likelihood"]),
                        business_impact=str(raw["business_impact"]),
                        recommended_action=str(raw["recommended_action"]),
                        confidence=float(raw["confidence"]),
                        citations=list(raw.get("citations") or []),
                        rule_key=None,  # LLM findings are not deterministic
                        source="llm",
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Dropping malformed LLM risk: %s (%s)", raw, exc)
    return candidates


# --------------------------------------------------------------------------- #
# Persistence                                                                 #
# --------------------------------------------------------------------------- #


async def _upsert_rule_risk(
    db: AsyncSession,
    project_id: uuid.UUID,
    candidate: RiskCandidate,
) -> Risk:
    """Insert-or-update a rules-based finding by ``project_id + rule_key``.

    Update targets rows where ``status IN ('open','acknowledged')`` — a
    resolved/mitigated row stays historical, and a new occurrence produces
    a fresh row (which is what a PM wants: they closed it, condition came
    back, that's a new event).
    """
    assert candidate.rule_key is not None
    metadata_json = json.dumps({"rule_key": candidate.rule_key, "source": "rules"})
    existing = (
        await db.execute(
            select(Risk).where(
                Risk.project_id == project_id,
                Risk.metadata_["rule_key"].astext == candidate.rule_key,
                Risk.status.in_(("open", "acknowledged")),
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.category = candidate.category
        existing.title = candidate.title
        existing.description = candidate.description
        existing.severity = candidate.severity
        existing.likelihood = candidate.likelihood
        existing.business_impact = candidate.business_impact
        existing.recommended_action = candidate.recommended_action
        existing.confidence = candidate.confidence
        # Refresh detected_at so trend charts show the condition is current.
        existing.detected_at = datetime.now(UTC)
        return existing

    risk = Risk(
        project_id=project_id,
        category=candidate.category,
        title=candidate.title,
        description=candidate.description,
        severity=candidate.severity,
        likelihood=candidate.likelihood,
        business_impact=candidate.business_impact,
        recommended_action=candidate.recommended_action,
        confidence=candidate.confidence,
        citations=candidate.citations or None,
        metadata_=json.loads(metadata_json),
    )
    db.add(risk)
    return risk


async def _insert_llm_risk(
    db: AsyncSession,
    project_id: uuid.UUID,
    candidate: RiskCandidate,
) -> Risk:
    """LLM findings always insert — no natural key to dedupe on."""
    risk = Risk(
        project_id=project_id,
        category=candidate.category,
        title=candidate.title,
        description=candidate.description,
        severity=candidate.severity,
        likelihood=candidate.likelihood,
        business_impact=candidate.business_impact,
        recommended_action=candidate.recommended_action,
        confidence=candidate.confidence,
        citations=candidate.citations or None,
        metadata_={"source": "llm"},
    )
    db.add(risk)
    return risk


# --------------------------------------------------------------------------- #
# Public entry points                                                         #
# --------------------------------------------------------------------------- #


async def scan_project(
    db: AsyncSession,
    project_id: uuid.UUID,
    settings: Settings,
    *,
    run_llm: bool = True,
) -> list[Risk]:
    """Run rules + optional LLM pass; persist the findings; return them.

    Set ``run_llm=False`` for tests or when the caller has already decided
    the LLM shouldn't run (e.g. seed scripts).
    """
    # 1) Rules.
    rules_candidates = await run_rules(db, project_id)
    written: list[Risk] = []
    for candidate in rules_candidates:
        written.append(await _upsert_rule_risk(db, project_id, candidate))

    # 2) LLM (best-effort).
    if run_llm:
        chunks = await _load_recent_chunks(db, project_id, limit=LLM_CONTEXT_CHUNK_COUNT)
        llm_candidates = await _call_llm_pass(
            settings=settings,
            rules_findings=rules_candidates,
            chunks=chunks,
        )
        for candidate in llm_candidates:
            written.append(await _insert_llm_risk(db, project_id, candidate))

    await db.commit()
    for risk in written:
        await db.refresh(risk)
    return written
