"""Generated reports (markdown source of truth + optional rendered artifacts)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from pmx_api.db.models.base import Base

REPORT_KINDS = ("executive", "weekly", "monthly", "risk_only")


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('executive','weekly','monthly','risk_only')",
            name="reports_kind_check",
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
    generated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'executive'"))
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    docx_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
