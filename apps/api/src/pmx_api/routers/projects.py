"""Projects router — create, list, detail (M1 scope).

Every endpoint is org-scoped via ``resolve_tenant``. ``org_id`` is *never*
taken from the client; it's derived from the authenticated user's mirrored
row. That way the API can't be tricked into cross-tenant reads even if a
caller forges an ``org_id`` in the payload.

Update / archive endpoints are deferred to M2 per DR-002 (M1 = create + list
+ detail only, wired to real data).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from pmx_api.db.models import Project
from pmx_api.deps import (
    CurrentUser,
    DBSession,
    require_current_user,
    resolve_tenant,
)

router = APIRouter(prefix="/v1/projects", tags=["projects"])


# --------------------------------------------------------------------------- #
# Schemas                                                                     #
# --------------------------------------------------------------------------- #


class ProjectCreate(BaseModel):
    """Fields a caller may set at create time. Everything else is server-owned."""

    name: str = Field(min_length=1, max_length=200)
    client: str | None = Field(default=None, max_length=200)
    sector: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)


class ProjectRead(BaseModel):
    """Wire representation. UUIDs serialised as strings for JSON portability."""

    id: str
    org_id: str
    name: str
    client: str | None
    sector: str | None
    location: str | None
    status: str
    health_score: int | None
    created_at: datetime
    updated_at: datetime


def _to_read(project: Project) -> ProjectRead:
    return ProjectRead(
        id=str(project.id),
        org_id=str(project.org_id),
        name=project.name,
        client=project.client,
        sector=project.sector,
        location=project.location,
        status=project.status,
        health_score=project.health_score,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


# --------------------------------------------------------------------------- #
# Routes                                                                      #
# --------------------------------------------------------------------------- #


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project (scoped to caller's org)",
)
async def create_project(
    payload: ProjectCreate,
    db: DBSession,
    current: Annotated[CurrentUser, Depends(require_current_user)],
) -> ProjectRead:
    tenant = await resolve_tenant(db, current)

    project = Project(
        org_id=uuid.UUID(tenant.org_uuid),
        name=payload.name,
        client=payload.client,
        sector=payload.sector,
        location=payload.location,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return _to_read(project)


@router.get(
    "",
    response_model=list[ProjectRead],
    summary="List projects visible to the caller (org-scoped)",
)
async def list_projects(
    db: DBSession,
    current: Annotated[CurrentUser, Depends(require_current_user)],
) -> list[ProjectRead]:
    tenant = await resolve_tenant(db, current)

    # We surface only active/on_hold — archived rows stay hidden by default so
    # a busy list view doesn't drown in stale data. Filtering UX lands in M2.
    stmt = (
        select(Project)
        .where(Project.org_id == uuid.UUID(tenant.org_uuid))
        .order_by(Project.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_read(row) for row in rows]


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Get a project by id (404 if not in caller's org)",
)
async def get_project(
    project_id: uuid.UUID,
    db: DBSession,
    current: Annotated[CurrentUser, Depends(require_current_user)],
) -> ProjectRead:
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
        # Mask cross-tenant existence: same 404 whether the row doesn't exist
        # or belongs to another org. Prevents id enumeration probes.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return _to_read(project)
