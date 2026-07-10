# pmx-api

FastAPI backend for [PMX AI — Project Risk Copilot](../../DESIGN.md).

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) for dependency management

## Setup

```bash
cp .env.example .env
uv sync
```

## Run

```bash
# Dev server with auto-reload
uv run pmx-api

# Or via FastAPI CLI
uv run fastapi dev src/pmx_api/main.py
```

Server binds to `http://127.0.0.1:8000`. Docs live at `/docs`.

## Test

```bash
uv run pytest
```

## Lint / typecheck

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

## Database (M0.3)

Postgres 15+ with pgvector 0.7+. Neon is the canonical target.

```bash
# 1. Set DATABASE_URL in .env (see .env.example for accepted formats).
#    Any of these work — session.py normalises to psycopg 3:
#      postgres://…, postgresql://…, postgresql+psycopg://…
export DATABASE_URL=postgresql+psycopg://user:pass@host:5432/pmx

# 2. Apply migrations
uv run alembic upgrade head

# 3. (Optional) point at a one-off DB without editing .env
uv run alembic -x db_url=postgresql://user:pass@host/db upgrade head

# Preview the SQL Alembic will emit without running it
uv run alembic upgrade head --sql
```

The first migration (`001_initial`) enables the pgvector extension and creates
every table from [DESIGN.md](../../DESIGN.md) §4, including the HNSW index on
`document_chunks.embedding` (`m=16`, `ef_construction=64`).

## Project layout

```
apps/api/
├── pyproject.toml
├── uv.lock
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 001_initial.py    # DESIGN §4 schema
├── .python-version
├── .env.example
├── src/pmx_api/
│   ├── __init__.py
│   ├── main.py            # FastAPI factory + CLI entry
│   ├── config.py          # Pydantic Settings (reads DATABASE_URL)
│   ├── observability.py   # Logfire wiring
│   ├── deps.py            # get_db() async session dep
│   ├── db/
│   │   ├── __init__.py
│   │   ├── session.py     # sync + async engine + session factory
│   │   └── models/        # one file per aggregate root
│   │       ├── base.py
│   │       ├── organization.py
│   │       ├── user.py
│   │       ├── project.py
│   │       ├── document.py
│   │       ├── structured.py
│   │       ├── risk.py
│   │       ├── health.py
│   │       ├── chat.py
│   │       ├── report.py
│   │       ├── notification.py
│   │       └── event.py
│   └── routers/
│       ├── health.py      # GET /v1/health
│       └── me.py          # GET /v1/me (stub until M0.4 auth)
└── tests/
    ├── test_health.py
    └── test_db.py         # hermetic model + metadata checks
```

## Endpoints (M0.2)

| Method | Path              | Purpose                             |
|--------|-------------------|-------------------------------------|
| GET    | `/v1/health`      | Liveness probe with uptime seconds  |
| GET    | `/v1/me`          | Auth stub (real impl in M0.4)       |
| GET    | `/docs`           | Interactive OpenAPI docs            |
| GET    | `/openapi.json`   | Machine-readable schema             |

## Milestones

- **M0.2:** app scaffold, health, CORS, Logfire wiring.
- **M0.3 (this):** Postgres + pgvector + Alembic; SQLAlchemy 2 models for the DESIGN §4 schema.
- **M0.4:** Clerk JWT verification middleware, real `/v1/me`.
- **M1:** projects CRUD, uploads, extraction, risk engine, chat.
