"""Risks router — list / detail / status-patch / scan (M2 scope).

Every endpoint is org-scoped through the same ``resolve_tenant`` +
``project.org_id`` check the M1 routers use. The scan endpoint is
synchronous for M2 — DR-002's async-worker migration lands in M3.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from pmx_api.config import Settings, get_settings
from pmx_api.db.models import Project, Risk
from pmx_api.db.models.risk import RISK_CATEGORIES, RISK_STATUSES
from pmx_api.deps import (
    CurrentUser,
    DBSession,
    TenantContext,
    require_current_user,
    resolve_tenant,
)
from pmx_api.services import risks as risks_service

# Note: two prefixes here — the project-scoped list/scan lives under
# /v1/projects/{project_id}/risks, and the detail/patch under /v1/risks/{id}.
# We mount two routers on the same tag rather than a nested router because
# DESIGN §5's URL shape splits by ownership vs identity.
project_scoped_router = APIRouter(
    prefix="/v1/projects/{project_id}/risks",
    tags=["risks"],
)
risk_scoped_router = APIRouter(prefix="/v1/risks", tags=["risks"])


# --------------------------------------------------------------------------- #
# Schemas                                                                     #
# --------------------------------------------------------------------------- #


class RiskRead(BaseModel):
    """Wire representation of a risk row.

    JSON-safe: UUIDs as strings, timestamps as ISO strings. Citations pass
    through as the raw JSONB list (each entry is ``{document_id, chunk_id,
    page}``).
    """

    id: str
    project_id: str
    category: str
    title: str
    description: str
    severity: int
    likelihood: float
    business_impact: str
    recommended_action: str
    confidence: float
    status: str
    detected_at: datetime
    resolved_at: datetime | None
    citations: list[dict[str, Any]] | None
    source: str = Field(
        description="Which pass emitted this risk: 'rules' or 'llm'.",
    )
    rule_key: str | None = Field(
        default=None,
        description="Stable dedup key for rules-based risks; null for LLM findings.",
    )


class RiskPatch(BaseModel):
    """Status transitions the UI can trigger from the risk drawer."""

    status: Literal["open", "acknowledged", "mitigated", "resolved"]


class ScanResponse(BaseModel):
    """Envelope returned by the sync scan endpoint."""

    new_or_updated: list[RiskRead]
    total: int


def _to_read(risk: Risk) -> RiskRead:
    meta = risk.metadata_ or {}
    return RiskRead(
        id=str(risk.id),
        project_id=str(risk.project_id),
        category=risk.category,
        title=risk.title,
        description=risk.description,
        severity=risk.severity,
        likelihood=float(risk.likelihood),
        business_impact=risk.business_impact,
        recommended_action=risk.recommended_action,
        confidence=float(risk.confidence),
        status=risk.status,
        detected_at=risk.detected_at,
        resolved_at=risk.resolved_at,
        citations=risk.citations,
        source=str(meta.get("source", "rules")),
        rule_key=(
            str(meta["rule_key"])
            if isinstance(meta, dict) and meta.get("rule_key") is not None
            else None
        ),
    )


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


async def _load_risk_scoped(db: DBSession, risk_id: uuid.UUID, tenant: TenantContext) -> Risk:
    """Fetch a risk, verifying its project belongs to the caller's org."""
    row = (
        await db.execute(
            select(Risk, Project)
            .join(Project, Project.id == Risk.project_id)
            .where(
                Risk.id == risk_id,
                Project.org_id == uuid.UUID(tenant.org_uuid),
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Risk not found",
        )
    risk: Risk = row[0]
    return risk


# --------------------------------------------------------------------------- #
# Project-scoped routes                                                       #
# --------------------------------------------------------------------------- #


@project_scoped_router.get(
    "",
    response_model=list[RiskRead],
    summary="List risks for a project (filter: category, severity_gte, status)",
)
async def list_risks(
    project_id: uuid.UUID,
    db: DBSession,
    current: Annotated[CurrentUser, Depends(require_current_user)],
    category: Annotated[str | None, Query(description="One of RISK_CATEGORIES")] = None,
    severity_gte: Annotated[int | None, Query(ge=1, le=5)] = None,
    risk_status: Annotated[
        str | None,
        Query(alias="status", description="One of RISK_STATUSES"),
    ] = None,
) -> list[RiskRead]:
    tenant = await resolve_tenant(db, current)
    await _load_project_scoped(db, project_id, tenant)

    if category is not None and category not in RISK_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"category must be one of {RISK_CATEGORIES}",
        )
    if risk_status is not None and risk_status not in RISK_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"status must be one of {RISK_STATUSES}",
        )

    stmt = select(Risk).where(Risk.project_id == project_id)
    if category is not None:
        stmt = stmt.where(Risk.category == category)
    if severity_gte is not None:
        stmt = stmt.where(Risk.severity >= severity_gte)
    if risk_status is not None:
        stmt = stmt.where(Risk.status == risk_status)
    stmt = stmt.order_by(Risk.severity.desc(), Risk.detected_at.desc())

    rows = (await db.execute(stmt)).scalars().all()
    return [_to_read(r) for r in rows]


@project_scoped_router.post(
    "/scan",
    response_model=ScanResponse,
    summary="Trigger a risk scan (rules + LLM). Sync for M2 per DR-002.",
)
async def scan_risks(
    project_id: uuid.UUID,
    db: DBSession,
    current: Annotated[CurrentUser, Depends(require_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ScanResponse:
    tenant = await resolve_tenant(db, current)
    await _load_project_scoped(db, project_id, tenant)

    written = await risks_service.scan_project(db, project_id, settings)
    reads = [_to_read(r) for r in written]
    return ScanResponse(new_or_updated=reads, total=len(reads))


# --------------------------------------------------------------------------- #
# Risk-scoped routes                                                          #
# --------------------------------------------------------------------------- #


@risk_scoped_router.get(
    "/{risk_id}",
    response_model=RiskRead,
    summary="Get a risk by id (with citations)",
)
async def get_risk(
    risk_id: uuid.UUID,
    db: DBSession,
    current: Annotated[CurrentUser, Depends(require_current_user)],
) -> RiskRead:
    tenant = await resolve_tenant(db, current)
    risk = await _load_risk_scoped(db, risk_id, tenant)
    return _to_read(risk)


@risk_scoped_router.patch(
    "/{risk_id}",
    response_model=RiskRead,
    summary="Change a risk's status (acknowledge / mitigate / resolve)",
)
async def patch_risk(
    risk_id: uuid.UUID,
    body: RiskPatch,
    db: DBSession,
    current: Annotated[CurrentUser, Depends(require_current_user)],
) -> RiskRead:
    tenant = await resolve_tenant(db, current)
    risk = await _load_risk_scoped(db, risk_id, tenant)

    risk.status = body.status
    if body.status == "resolved":
        risk.resolved_at = datetime.now(UTC)
    elif risk.resolved_at is not None and body.status in {"open", "acknowledged"}:
        # Reopening a resolved risk clears the resolved marker so trend charts
        # don't show it as still-resolved.
        risk.resolved_at = None

    await db.commit()
    await db.refresh(risk)
    return _to_read(risk)
