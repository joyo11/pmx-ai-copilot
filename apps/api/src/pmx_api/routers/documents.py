"""Documents router — upload + list (M1 scope, PDF only).

Design notes:

* We enforce PDF-only at the MIME layer (``application/pdf``). Other kinds
  return **415 Unsupported Media Type** so the frontend gets a clean error
  instead of a mysterious extraction failure.
* Files land on local disk under ``{storage_dir}/{document_id}.pdf``. R2 is
  the M2 target — see DR-002. We record the on-disk path in ``storage_uri``
  as a ``file://`` URL so the same field can hold R2 URIs later without a
  schema change.
* Extraction runs **inline** on the request. That's acceptable for M1 (PDFs
  are small, and the demo isn't concurrent). M2 hands this off to RQ.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy import select

from pmx_api.config import Settings, get_settings
from pmx_api.db.models import Document, Project
from pmx_api.deps import (
    CurrentUser,
    DBSession,
    TenantContext,
    require_current_user,
    resolve_tenant,
)
from pmx_api.pipeline.extract import extract_and_embed_document

router = APIRouter(prefix="/v1/projects/{project_id}/documents", tags=["documents"])

PDF_MIME = "application/pdf"


# --------------------------------------------------------------------------- #
# Schemas                                                                     #
# --------------------------------------------------------------------------- #


class DocumentUploadResponse(BaseModel):
    """What the client sees after a successful upload."""

    document_id: str
    status: str


class DocumentRead(BaseModel):
    """List/get row shape."""

    id: str
    project_id: str
    filename: str
    kind: str
    status: str
    bytes: int | None
    uploaded_at: datetime
    processed_at: datetime | None
    error: str | None


def _to_read(document: Document) -> DocumentRead:
    return DocumentRead(
        id=str(document.id),
        project_id=str(document.project_id),
        filename=document.filename,
        kind=document.kind,
        status=document.status,
        bytes=document.bytes,
        uploaded_at=document.uploaded_at,
        processed_at=document.processed_at,
        error=document.error,
    )


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


async def _load_project_scoped(
    db: DBSession,
    project_id: uuid.UUID,
    tenant: TenantContext,
) -> Project:
    """Fetch a project the caller is allowed to see, or 404."""
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


def _storage_dir(settings: Settings) -> Path:
    """Resolve + create the on-disk storage root.

    Relative paths land next to wherever the API is invoked. That's fine for
    the M1 demo (Render's disk); prod switches to R2 in M2.
    """
    directory = Path(settings.storage_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


# --------------------------------------------------------------------------- #
# Routes                                                                      #
# --------------------------------------------------------------------------- #


@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF and run extraction inline",
)
async def upload_document(
    project_id: uuid.UUID,
    db: DBSession,
    current: Annotated[CurrentUser, Depends(require_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    file: Annotated[UploadFile, File(description="PDF only (M1 scope).")],
) -> DocumentUploadResponse:
    tenant = await resolve_tenant(db, current)
    project = await _load_project_scoped(db, project_id, tenant)

    if file.content_type != PDF_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Only {PDF_MIME} is supported in M1 (got {file.content_type!r})",
        )

    # Persist to disk under a fresh UUID. We generate the id client-side so
    # the storage path and the DB row agree, and we can clean up on failure.
    document_id = uuid.uuid4()
    dest = _storage_dir(settings) / f"{document_id}.pdf"
    contents = await file.read()
    dest.write_bytes(contents)

    document = Document(
        id=document_id,
        project_id=project.id,
        uploaded_by=uuid.UUID(tenant.user_uuid),
        kind="pdf_generic",
        filename=file.filename or f"{document_id}.pdf",
        storage_uri=f"file://{dest.resolve()}",
        bytes=len(contents),
        status="uploaded",
    )
    db.add(document)
    await db.commit()

    # Inline extraction. If it fails, the document row stays with status='failed'
    # and the client gets a 500 — they can retry by re-uploading.
    try:
        await extract_and_embed_document(
            db=db,
            document_id=document.id,
            project_id=project.id,
            pdf_path=dest,
            settings=settings,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction failed: {exc}",
        ) from exc

    await db.refresh(document)
    return DocumentUploadResponse(
        document_id=str(document.id),
        status=document.status,
    )


@router.get(
    "",
    response_model=list[DocumentRead],
    summary="List documents for a project",
)
async def list_documents(
    project_id: uuid.UUID,
    db: DBSession,
    current: Annotated[CurrentUser, Depends(require_current_user)],
) -> list[DocumentRead]:
    tenant = await resolve_tenant(db, current)
    await _load_project_scoped(db, project_id, tenant)

    stmt = (
        select(Document)
        .where(Document.project_id == project_id)
        .order_by(Document.uploaded_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_read(row) for row in rows]
