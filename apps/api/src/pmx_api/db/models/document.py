"""Documents + chunks — the RAG substrate."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from pmx_api.db.models.base import Base

DOCUMENT_KINDS = (
    "schedule_p6",
    "schedule_mpp",
    "budget_xlsx",
    "rfi_log",
    "meeting_notes",
    "daily_report",
    "change_order",
    "pdf_generic",
    "docx_generic",
    "transcript",
)

DOCUMENT_STATUSES = ("uploaded", "extracting", "embedding", "ready", "failed")

# text-embedding-3-large returns 3072 dims.
EMBEDDING_DIMS = 3072


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('schedule_p6','schedule_mpp','budget_xlsx','rfi_log',"
            "'meeting_notes','daily_report','change_order',"
            "'pdf_generic','docx_generic','transcript')",
            name="documents_kind_check",
        ),
        CheckConstraint(
            "status IN ('uploaded','extracting','embedding','ready','failed')",
            name="documents_status_check",
        ),
        Index("ix_documents_project_id_kind", "project_id", "kind"),
        Index(
            "ix_documents_status_not_ready",
            "status",
            postgresql_where=text("status != 'ready'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    storage_uri: Mapped[str] = mapped_column(String, nullable=False)
    bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'uploaded'"))
    extracted_text_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_document_chunks_project_id", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMS), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
