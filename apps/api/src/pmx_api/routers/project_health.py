"""Project health-score endpoints (DESIGN §5).

Separate router from ``routers/health.py`` (liveness probe) so the two
concerns stay unambiguous — the URL patterns are ``/v1/projects/{id}/health*``
here vs ``/v1/health`` there.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from pmx_api.db.models import HealthSnapshot, Project
from pmx_api.deps import (
    CurrentUser,
    DBSession,
    TenantContext,
    require_current_user,
    resolve_tenant,
)
from pmx_api.services import health as health_service

router = APIRouter(prefix="/v1/projects/{project_id}/health", tags=["health"])


# --------------------------------------------------------------------------- #
# Schemas                                                                     #
# --------------------------------------------------------------------------- #


class HealthSnapshotRead(BaseModel):
    """Wire shape of a ``health_snapshots`` row.

    ``factors`` is left as a dict of ``{factor_key: {label, value, sub_score,
    weight, detail}}`` so the UI can render both the number and the natural
    language ``detail`` per factor.
    """

    id: str
    project_id: str
    score: int
    factors: dict[str, Any] = Field(default_factory=dict)
    reasoning: str | None
    computed_at: datetime


def _to_read(snapshot: HealthSnapshot) -> HealthSnapshotRead:
    return HealthSnapshotRead(
        id=str(snapshot.id),
        project_id=str(snapshot.project_id),
        score=snapshot.score,
        factors=dict(snapshot.factors) if snapshot.factors else {},
        reasoning=snapshot.reasoning,
        computed_at=snapshot.computed_at,
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


# --------------------------------------------------------------------------- #
# Routes                                                                      #
# --------------------------------------------------------------------------- #


@router.get(
    "",
    response_model=HealthSnapshotRead,
    summary="Latest health snapshot for a project",
)
async def get_latest_health(
    project_id: uuid.UUID,
    db: DBSession,
    current: Annotated[CurrentUser, Depends(require_current_user)],
) -> HealthSnapshotRead:
    tenant = await resolve_tenant(db, current)
    await _load_project_scoped(db, project_id, tenant)

    snapshot = await health_service.latest_snapshot(db, project_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No health snapshot yet — run POST /health/recompute",
        )
    return _to_read(snapshot)


@router.post(
    "/recompute",
    response_model=HealthSnapshotRead,
    status_code=status.HTTP_201_CREATED,
    summary="Recompute health score and insert a fresh snapshot",
)
async def recompute_health(
    project_id: uuid.UUID,
    db: DBSession,
    current: Annotated[CurrentUser, Depends(require_current_user)],
) -> HealthSnapshotRead:
    tenant = await resolve_tenant(db, current)
    await _load_project_scoped(db, project_id, tenant)

    snapshot = await health_service.snapshot_project_health(db, project_id)
    return _to_read(snapshot)


@router.get(
    "/history",
    response_model=list[HealthSnapshotRead],
    summary="Last 30 health snapshots for the project (newest first)",
)
async def get_health_history(
    project_id: uuid.UUID,
    db: DBSession,
    current: Annotated[CurrentUser, Depends(require_current_user)],
) -> list[HealthSnapshotRead]:
    tenant = await resolve_tenant(db, current)
    await _load_project_scoped(db, project_id, tenant)

    snapshots = await health_service.recent_snapshots(db, project_id, limit=30)
    return [_to_read(s) for s in snapshots]
