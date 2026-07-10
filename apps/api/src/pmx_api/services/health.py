"""Health-score service — 0..100 rollup per project (DESIGN §4 factors).

Score is a weighted sum of five factor sub-scores. Each factor returns 0..1
where 1 = healthy and 0 = worst-case; the weighted sum is scaled to 0..100
and rounded to int for the ``health_snapshots.score`` column.

Weights (from the task spec):
  * budget_variance          25
  * schedule_variance        25
  * open_risk_count          20  (weighted by severity)
  * overdue_rfi_count        15
  * document_ingestion_health 15

The factor payload is stored in ``health_snapshots.factors`` as a JSONB
object so the UI can render "why is this project 71/100" from the same row.
A one-paragraph natural-language ``reasoning`` string lands in
``health_snapshots.reasoning`` for the drawer view.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from pmx_api.db.models import HealthSnapshot, Project

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Weight vector (must sum to 100)                                             #
# --------------------------------------------------------------------------- #

WEIGHT_BUDGET_VARIANCE = 25
WEIGHT_SCHEDULE_VARIANCE = 25
WEIGHT_OPEN_RISKS = 20
WEIGHT_OVERDUE_RFIS = 15
WEIGHT_DOC_INGEST = 15

assert (
    WEIGHT_BUDGET_VARIANCE
    + WEIGHT_SCHEDULE_VARIANCE
    + WEIGHT_OPEN_RISKS
    + WEIGHT_OVERDUE_RFIS
    + WEIGHT_DOC_INGEST
    == 100
), "health-score weights must sum to 100"

# Sub-score calibration constants — deliberately conservative defaults that
# a PM would eyeball as reasonable. Relax with evidence per feedback rule.
BUDGET_VARIANCE_PENALTY_CAP = 0.25  # 25% over forecast = 0.0 sub-score
SCHEDULE_SLIP_DAYS_CAP = 30  # 30d slip on worst task = 0.0 sub-score
OPEN_RISK_SEVERITY_CAP = 15  # sum of severities that flatlines the sub-score
OVERDUE_RFI_CAP = 5  # 5+ overdue RFIs flatlines the sub-score
DOC_HEALTHY_STATUSES = ("ready",)

RFI_AGING_DAYS = 14


# --------------------------------------------------------------------------- #
# Data types                                                                  #
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class Factor:
    """One numbered contribution to the overall score.

    ``value`` is the raw metric (dollars, days, count); ``sub_score`` is the
    0..1 normalisation the weighting uses. Both surface in the JSONB so the
    UI can explain the number in whichever unit reads best.
    """

    key: str
    label: str
    value: float
    sub_score: float
    weight: int
    detail: str


@dataclass(slots=True)
class HealthResult:
    """What ``compute_project_health`` returns to callers who don't want the ORM row."""

    score: int
    factors: list[Factor]
    reasoning: str


# --------------------------------------------------------------------------- #
# Factor calculators                                                          #
# --------------------------------------------------------------------------- #


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


async def _factor_budget_variance(db: AsyncSession, project_id: uuid.UUID) -> Factor:
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

    if forecast <= 0:
        # No forecast yet — neutral score so an empty project doesn't get
        # penalised. Onboarding UX handles the "no data" case in copy.
        return Factor(
            key="budget_variance",
            label="Budget variance",
            value=0.0,
            sub_score=1.0,
            weight=WEIGHT_BUDGET_VARIANCE,
            detail="No budget forecast on file yet — factor treated as neutral.",
        )

    overrun = max(0.0, (actual - forecast) / forecast)
    sub = 1.0 - _clamp(overrun / BUDGET_VARIANCE_PENALTY_CAP)
    return Factor(
        key="budget_variance",
        label="Budget variance",
        value=round(overrun, 4),
        sub_score=round(sub, 4),
        weight=WEIGHT_BUDGET_VARIANCE,
        detail=(
            f"Actual ${actual / 100:,.2f} vs forecast ${forecast / 100:,.2f} "
            f"→ {overrun * 100:.1f}% overrun."
        ),
    )


async def _factor_schedule_variance(db: AsyncSession, project_id: uuid.UUID) -> Factor:
    row = (
        await db.execute(
            text(
                """
                SELECT COALESCE(MAX(slip_days), 0) AS worst_slip,
                       COUNT(*) FILTER (WHERE slip_days > 0) AS slipping_tasks,
                       COUNT(*) AS total_tasks
                FROM schedule_tasks
                WHERE project_id = :pid
                """
            ),
            {"pid": project_id},
        )
    ).one()
    worst = int(row.worst_slip)
    slipping = int(row.slipping_tasks)
    total = int(row.total_tasks)

    if total == 0:
        return Factor(
            key="schedule_variance",
            label="Schedule variance",
            value=0.0,
            sub_score=1.0,
            weight=WEIGHT_SCHEDULE_VARIANCE,
            detail="No schedule tasks on file yet — factor treated as neutral.",
        )

    sub = 1.0 - _clamp(worst / SCHEDULE_SLIP_DAYS_CAP)
    return Factor(
        key="schedule_variance",
        label="Schedule variance",
        value=float(worst),
        sub_score=round(sub, 4),
        weight=WEIGHT_SCHEDULE_VARIANCE,
        detail=(
            f"Worst slip {worst} days across {slipping}/{total} tasks."
            if slipping
            else f"No tasks slipping across {total} tracked."
        ),
    )


async def _factor_open_risks(db: AsyncSession, project_id: uuid.UUID) -> Factor:
    """Sum of severities on open risks, capped for the sub-score."""
    row = (
        await db.execute(
            text(
                """
                SELECT COUNT(*) AS open_count,
                       COALESCE(SUM(severity), 0) AS severity_sum
                FROM risks
                WHERE project_id = :pid
                  AND status IN ('open', 'acknowledged')
                """
            ),
            {"pid": project_id},
        )
    ).one()
    open_count = int(row.open_count)
    severity_sum = int(row.severity_sum)

    sub = 1.0 - _clamp(severity_sum / OPEN_RISK_SEVERITY_CAP)
    return Factor(
        key="open_risk_count",
        label="Open risks (severity-weighted)",
        value=float(severity_sum),
        sub_score=round(sub, 4),
        weight=WEIGHT_OPEN_RISKS,
        detail=(f"{open_count} open/acknowledged risk(s), total severity {severity_sum}."),
    )


async def _factor_overdue_rfis(db: AsyncSession, project_id: uuid.UUID) -> Factor:
    cutoff = datetime.now(UTC).date() - timedelta(days=RFI_AGING_DAYS)
    row = (
        await db.execute(
            text(
                """
                SELECT COUNT(*) AS overdue_count
                FROM rfis
                WHERE project_id = :pid
                  AND status = 'open'
                  AND submitted_date IS NOT NULL
                  AND submitted_date <= :cutoff
                """
            ),
            {"pid": project_id, "cutoff": cutoff},
        )
    ).one()
    overdue = int(row.overdue_count)
    sub = 1.0 - _clamp(overdue / OVERDUE_RFI_CAP)
    return Factor(
        key="overdue_rfi_count",
        label="Overdue RFIs",
        value=float(overdue),
        sub_score=round(sub, 4),
        weight=WEIGHT_OVERDUE_RFIS,
        detail=(
            f"{overdue} RFI(s) open for more than {RFI_AGING_DAYS} days."
            if overdue
            else "No RFIs beyond the 14-day age threshold."
        ),
    )


async def _factor_doc_ingest_health(db: AsyncSession, project_id: uuid.UUID) -> Factor:
    """% of documents currently in a healthy status."""
    row = (
        await db.execute(
            text(
                """
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE status = ANY(:healthy)) AS healthy
                FROM documents
                WHERE project_id = :pid
                """
            ),
            {"pid": project_id, "healthy": list(DOC_HEALTHY_STATUSES)},
        )
    ).one()
    total = int(row.total)
    healthy = int(row.healthy)

    if total == 0:
        return Factor(
            key="document_ingestion_health",
            label="Document ingestion health",
            value=1.0,
            sub_score=1.0,
            weight=WEIGHT_DOC_INGEST,
            detail="No documents uploaded yet — factor treated as neutral.",
        )

    ratio = healthy / total
    return Factor(
        key="document_ingestion_health",
        label="Document ingestion health",
        value=round(ratio, 4),
        sub_score=round(ratio, 4),
        weight=WEIGHT_DOC_INGEST,
        detail=f"{healthy}/{total} documents in ready status.",
    )


# --------------------------------------------------------------------------- #
# Rollup                                                                      #
# --------------------------------------------------------------------------- #


def _factors_to_dict(factors: list[Factor]) -> dict[str, Any]:
    """Serialise factor list to the JSONB shape the ``factors`` column stores."""
    return {
        f.key: {
            "label": f.label,
            "value": f.value,
            "sub_score": f.sub_score,
            "weight": f.weight,
            "detail": f.detail,
        }
        for f in factors
    }


def _reasoning_paragraph(score: int, factors: list[Factor]) -> str:
    """Compose a human-readable ``reasoning`` string for the snapshot row."""
    # Rank factors by penalty (weight * (1 - sub_score)) — the biggest hurt
    # to the score first, so the UI reads top-down.
    ranked = sorted(
        factors,
        key=lambda f: f.weight * (1.0 - f.sub_score),
        reverse=True,
    )
    pieces = [f"Overall score {score}/100. Contributing factors, worst-hit first:"]
    for f in ranked:
        penalty = f.weight * (1.0 - f.sub_score)
        pieces.append(f"- {f.label}: {f.detail} (weight {f.weight}, -{penalty:.1f} pts)")
    return "\n".join(pieces)


async def compute_project_health(db: AsyncSession, project_id: uuid.UUID) -> HealthResult:
    """Run every factor calculator, weight, and return the rollup.

    Doesn't touch the DB apart from reads — persistence is the caller's job.
    """
    factors = [
        await _factor_budget_variance(db, project_id),
        await _factor_schedule_variance(db, project_id),
        await _factor_open_risks(db, project_id),
        await _factor_overdue_rfis(db, project_id),
        await _factor_doc_ingest_health(db, project_id),
    ]
    weighted_sum = sum(f.sub_score * f.weight for f in factors)
    score = round(_clamp(weighted_sum, 0.0, 100.0))
    return HealthResult(
        score=score,
        factors=factors,
        reasoning=_reasoning_paragraph(score, factors),
    )


async def snapshot_project_health(db: AsyncSession, project_id: uuid.UUID) -> HealthSnapshot:
    """Compute + persist a fresh snapshot, mirror the score onto ``projects``.

    The mirror lets the projects list rank/filter by ``health_score`` without
    joining every list query to the latest snapshot.
    """
    result = await compute_project_health(db, project_id)
    snapshot = HealthSnapshot(
        project_id=project_id,
        score=result.score,
        factors=_factors_to_dict(result.factors),
        reasoning=result.reasoning,
    )
    db.add(snapshot)
    now = datetime.now(UTC)
    await db.execute(
        update(Project)
        .where(Project.id == project_id)
        .values(health_score=result.score, health_computed_at=now)
    )
    await db.commit()
    await db.refresh(snapshot)
    return snapshot


async def latest_snapshot(db: AsyncSession, project_id: uuid.UUID) -> HealthSnapshot | None:
    """Return the most recent snapshot or None if the project has never been scored."""
    row = (
        await db.execute(
            text(
                """
                SELECT id, project_id, score, factors, reasoning, computed_at
                FROM health_snapshots
                WHERE project_id = :pid
                ORDER BY computed_at DESC
                LIMIT 1
                """
            ),
            {"pid": project_id},
        )
    ).one_or_none()
    if row is None:
        return None
    return HealthSnapshot(
        id=row.id,
        project_id=row.project_id,
        score=row.score,
        factors=row.factors,
        reasoning=row.reasoning,
        computed_at=row.computed_at,
    )


async def recent_snapshots(
    db: AsyncSession, project_id: uuid.UUID, limit: int = 30
) -> list[HealthSnapshot]:
    """Return the last ``limit`` snapshots (newest first) for a trend chart."""
    rows = (
        await db.execute(
            text(
                """
                SELECT id, project_id, score, factors, reasoning, computed_at
                FROM health_snapshots
                WHERE project_id = :pid
                ORDER BY computed_at DESC
                LIMIT :limit
                """
            ),
            {"pid": project_id, "limit": limit},
        )
    ).all()
    return [
        HealthSnapshot(
            id=row.id,
            project_id=row.project_id,
            score=row.score,
            factors=row.factors,
            reasoning=row.reasoning,
            computed_at=row.computed_at,
        )
        for row in rows
    ]
