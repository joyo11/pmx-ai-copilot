"""Risk engine output rows."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from pmx_api.db.models.base import Base

RISK_CATEGORIES = ("schedule", "budget", "operational", "communication", "compliance")

RISK_STATUSES = ("open", "acknowledged", "mitigated", "resolved")


class Risk(Base):
    __tablename__ = "risks"
    __table_args__ = (
        CheckConstraint(
            "category IN ('schedule','budget','operational','communication','compliance')",
            name="risks_category_check",
        ),
        CheckConstraint(
            "severity BETWEEN 1 AND 5",
            name="risks_severity_check",
        ),
        CheckConstraint(
            "status IN ('open','acknowledged','mitigated','resolved')",
            name="risks_status_check",
        ),
        Index(
            "ix_risks_project_id_status_severity",
            "project_id",
            "status",
            text("severity DESC"),
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
    category: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    likelihood: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    business_impact: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'open'"))
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    citations: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB, nullable=True)
