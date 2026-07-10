"""Structured extractions — schedule tasks, budget lines, RFIs, change orders, meetings."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from pmx_api.db.models.base import Base

RFI_DISCIPLINES = (
    "electrical",
    "mechanical",
    "civil",
    "architectural",
    "structural",
    "plumbing",
    "other",
)

RFI_STATUSES = ("open", "answered", "overdue", "closed")

CHANGE_ORDER_STATUSES = ("pending", "approved", "rejected")


class ScheduleTask(Base):
    __tablename__ = "schedule_tasks"
    __table_args__ = (
        Index("ix_schedule_tasks_project_id_is_critical", "project_id", "is_critical"),
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
    source_doc_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    percent_done: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    predecessors: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    slip_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class BudgetLine(Base):
    __tablename__ = "budget_lines"
    __table_args__ = (Index("ix_budget_lines_project_id_period", "project_id", "period"),)

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
    source_doc_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    budgeted_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actual_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    forecast_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    period: Mapped[date | None] = mapped_column(Date, nullable=True)


class Rfi(Base):
    __tablename__ = "rfis"
    __table_args__ = (
        CheckConstraint(
            "discipline IN ('electrical','mechanical','civil','architectural',"
            "'structural','plumbing','other')",
            name="rfis_discipline_check",
        ),
        CheckConstraint(
            "status IN ('open','answered','overdue','closed')",
            name="rfis_status_check",
        ),
        Index("ix_rfis_project_id_status", "project_id", "status"),
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
    source_doc_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    number: Mapped[str | None] = mapped_column(String, nullable=True)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    discipline: Mapped[str | None] = mapped_column(String, nullable=True)
    submitted_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    answered_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    ai_delay_risk: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    ai_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)


class ChangeOrder(Base):
    __tablename__ = "change_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected')",
            name="change_orders_status_check",
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
    source_doc_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    number: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    submitted_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)


class Meeting(Base):
    __tablename__ = "meetings"

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
    source_doc_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    meeting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    decisions: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB, nullable=True)
    action_items: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB, nullable=True)
