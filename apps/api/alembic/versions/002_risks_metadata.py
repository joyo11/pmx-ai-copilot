"""Add ``metadata`` JSONB column to ``risks`` for rule-key deduplication.

The M2 risk engine emits a stable ``rule_key`` for every rules-based finding
(e.g. ``budget_overrun``, ``rfi_overdue_14d``). Storing that key inside the
row's ``metadata`` JSONB lets ``services.risks.scan_project`` re-run
idempotently: a subsequent scan updates the existing open row instead of
piling duplicate findings onto the same underlying condition.

We also add a partial GIN index on ``metadata->>'rule_key'`` so the dedup
lookup stays O(log n) as the risks table grows.

Revision ID: 002_risks_metadata
Revises: 001_initial
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "002_risks_metadata"
down_revision: str | Sequence[str] | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "risks",
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    # Partial index on the rule_key path — only rows that carry one qualify.
    op.execute(
        "CREATE INDEX ix_risks_project_id_rule_key "
        "ON risks (project_id, ((metadata->>'rule_key'))) "
        "WHERE metadata ? 'rule_key'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_risks_project_id_rule_key")
    op.drop_column("risks", "metadata")
