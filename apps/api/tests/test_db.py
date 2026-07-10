"""Hermetic DB-layer tests.

These do NOT touch a real Postgres. They just confirm the model package
imports cleanly and that ``Base.metadata`` sees every table listed in
DESIGN §4, plus the pgvector-backed embedding column.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Table

from pmx_api.db.models import Base
from pmx_api.db.session import (
    DatabaseNotConfiguredError,
    _to_async_url,
    _to_sync_url,
    reset_engines_for_tests,
)

EXPECTED_TABLES = {
    "organizations",
    "users",
    "projects",
    "project_members",
    "documents",
    "document_chunks",
    "schedule_tasks",
    "budget_lines",
    "rfis",
    "change_orders",
    "meetings",
    "risks",
    "health_snapshots",
    "chat_sessions",
    "chat_messages",
    "reports",
    "notifications",
    "events",
}


def test_metadata_contains_every_designed_table() -> None:
    """Every DESIGN §4 table is registered on Base.metadata."""
    tables = set(Base.metadata.tables.keys())
    missing = EXPECTED_TABLES - tables
    assert not missing, f"missing tables on Base.metadata: {sorted(missing)}"


def test_no_unexpected_tables() -> None:
    """No stray tables snuck in — schema stays intentional."""
    tables = set(Base.metadata.tables.keys())
    extra = tables - EXPECTED_TABLES
    assert not extra, f"unexpected tables on Base.metadata: {sorted(extra)}"


def test_document_chunks_has_vector_column() -> None:
    """document_chunks.embedding is a pgvector column with 3072 dims."""
    from pgvector.sqlalchemy import Vector

    table: Table = Base.metadata.tables["document_chunks"]
    embedding_col = table.c.embedding
    assert isinstance(embedding_col.type, Vector), (
        f"embedding column type = {embedding_col.type!r}, want Vector"
    )
    assert embedding_col.type.dim == 3072


def test_multi_tenant_tables_reference_org_or_project() -> None:
    """Every row-owned table is tenanted via org_id or via a chain through project_id."""
    org_scoped = {"users", "projects", "events"}
    project_scoped = {
        "documents",
        "document_chunks",
        "schedule_tasks",
        "budget_lines",
        "rfis",
        "change_orders",
        "meetings",
        "risks",
        "health_snapshots",
        "reports",
        "project_members",
    }
    for name in org_scoped:
        cols = Base.metadata.tables[name].c.keys()
        assert "org_id" in cols, f"{name} is missing org_id column"
    for name in project_scoped:
        cols = Base.metadata.tables[name].c.keys()
        assert "project_id" in cols, f"{name} is missing project_id column"


def test_hnsw_index_on_document_chunks_embedding() -> None:
    """HNSW index exists with the m=16 / ef_construction=64 parameters from DESIGN §4."""
    table = Base.metadata.tables["document_chunks"]
    hnsw = next(
        (idx for idx in table.indexes if idx.name == "ix_document_chunks_embedding_hnsw"),
        None,
    )
    assert hnsw is not None, "HNSW index on document_chunks.embedding missing"
    assert hnsw.dialect_kwargs.get("postgresql_using") == "hnsw"
    with_opts = hnsw.dialect_kwargs.get("postgresql_with") or {}
    assert with_opts.get("m") == 16
    assert with_opts.get("ef_construction") == 64


def test_check_constraints_present() -> None:
    """Sample the check constraints DESIGN §4 pins down.

    ``Base``'s naming convention prepends ``ck_<table>_``, so we match on suffix.
    """
    from sqlalchemy import CheckConstraint

    def constraint_names(table_name: str) -> set[str]:
        return {
            c.name
            for c in Base.metadata.tables[table_name].constraints
            if isinstance(c, CheckConstraint) and c.name
        }

    def has_suffix(names: set[str], suffix: str) -> bool:
        return any(n.endswith(suffix) for n in names)

    assert has_suffix(constraint_names("users"), "users_role_check")
    assert has_suffix(constraint_names("projects"), "projects_status_check")
    assert has_suffix(constraint_names("documents"), "documents_kind_check")
    assert has_suffix(constraint_names("documents"), "documents_status_check")
    assert has_suffix(constraint_names("risks"), "risks_category_check")
    assert has_suffix(constraint_names("risks"), "risks_severity_check")
    assert has_suffix(constraint_names("chat_messages"), "chat_messages_role_check")


def test_engine_helpers_reject_missing_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Engines refuse to build without DATABASE_URL rather than silently pointing at localhost."""
    from pmx_api import config

    monkeypatch.setenv("DATABASE_URL", "")
    config.get_settings.cache_clear()
    reset_engines_for_tests()

    with pytest.raises(DatabaseNotConfiguredError):
        from pmx_api.db.session import get_sync_engine

        get_sync_engine()

    config.get_settings.cache_clear()
    reset_engines_for_tests()


def test_url_normaliser_handles_common_variants() -> None:
    assert _to_sync_url("postgres://u:p@h/d") == "postgresql+psycopg://u:p@h/d"
    assert _to_sync_url("postgresql://u:p@h/d") == "postgresql+psycopg://u:p@h/d"
    assert _to_sync_url("postgresql+psycopg://u:p@h/d") == "postgresql+psycopg://u:p@h/d"
    assert _to_sync_url("postgresql+asyncpg://u:p@h/d") == "postgresql+psycopg://u:p@h/d"
    assert _to_async_url("postgres://u:p@h/d") == "postgresql+psycopg://u:p@h/d"
    assert _to_async_url("postgresql+asyncpg://u:p@h/d") == "postgresql+psycopg://u:p@h/d"


def test_get_db_dependency_is_async_iterator() -> None:
    """`get_db` is FastAPI-shaped: an async generator yielding an AsyncSession."""
    import inspect

    from pmx_api.deps import get_db

    assert inspect.isasyncgenfunction(get_db)
