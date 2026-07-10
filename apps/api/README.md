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
│   ├── pipeline/
│   │   ├── extract.py    # PDF -> chunks -> embeddings (M1)
│   │   └── retrieve.py   # pgvector cosine top-k retrieval
│   └── routers/
│       ├── health.py     # GET /v1/health
│       ├── me.py         # GET /v1/me
│       ├── projects.py   # M1 CRUD (create/list/get)
│       ├── documents.py  # M1 PDF upload + list
│       └── chat.py       # M1 SSE-streamed RAG chat
└── tests/
    ├── conftest.py       # fake CurrentUser + optional Postgres session
    ├── test_health.py
    ├── test_db.py        # hermetic model + metadata checks
    ├── test_auth.py      # Clerk JWT verification
    ├── test_projects.py  # M1 projects router (Postgres-gated)
    ├── test_documents.py # M1 upload + extraction (Postgres-gated)
    └── test_chat.py      # M1 SSE ordering (Postgres-gated)
```

## Endpoints (M1)

| Method | Path                                       | Purpose                                                    |
|--------|--------------------------------------------|------------------------------------------------------------|
| GET    | `/v1/health`                               | Liveness probe with uptime seconds                         |
| GET    | `/v1/me`                                   | Current Clerk user (tolerant of missing auth)              |
| POST   | `/v1/projects`                             | Create a project, scoped to caller's org                   |
| GET    | `/v1/projects`                             | List projects the caller can see                           |
| GET    | `/v1/projects/{id}`                        | Project detail (404 if outside caller's org)               |
| POST   | `/v1/projects/{id}/documents`              | Upload a PDF; runs extraction + embedding inline           |
| GET    | `/v1/projects/{id}/documents`              | List documents for a project                               |
| POST   | `/v1/projects/{id}/chat`                   | RAG chat over the project (SSE: token/citation/done/error) |
| GET    | `/docs`                                    | Interactive OpenAPI docs                                   |
| GET    | `/openapi.json`                            | Machine-readable schema                                    |

### M1 constraints (see DR-002)

- **PDF only** for uploads. Other MIME types return 415. XLSX / DOCX / P6 land in M2.
- **Local disk storage** — files land under `apps/api/storage/{document_id}.pdf`.
  R2 replaces this in M2 without a schema change (`storage_uri` already holds a
  URL).
- **Inline extraction** — the upload handler runs the pipeline synchronously.
  M2 hands the same function to an RQ worker.
- **No risk engine / schedule / budget / RFI classifier yet** — pure retrieval
  + citation chat for M1.

### SSE contract for `/v1/projects/{id}/chat`

```
event: citation
data: {"document_id": "...", "chunk_id": "...", "page": 3}

event: token
data: {"text": "The slab pour is scheduled for "}

event: token
data: {"text": "March 14 (p.3)."}

event: done
data: {"session_id": "..."}
```

An `error` event with `{"message": "..."}` may replace the tail if anything
fails after the stream has opened.

## Environment variables

Beyond the M0 set, M1 needs:

| Var                 | Required     | Notes                                                       |
|---------------------|--------------|-------------------------------------------------------------|
| `OPENAI_API_KEY`    | yes (uploads + chat) | Embeddings for chunk indexing and query retrieval.  |
| `ANTHROPIC_API_KEY` | yes (chat)   | Claude Sonnet 4.6 (adjust via `CHAT_MODEL` if renamed).     |
| `CHAT_MODEL`        | no           | Default `claude-sonnet-4-6`.                                |
| `EMBEDDING_MODEL`   | no           | Default `text-embedding-3-large` (3072 dims).               |
| `RETRIEVAL_TOP_K`   | no           | Default `8`.                                                |
| `STORAGE_DIR`       | no           | Default `storage`. Relative to the API's working directory. |

Tests that touch Postgres skip themselves unless `TEST_DATABASE_URL` points at
a Postgres 15+ instance with pgvector installed.

## Milestones

- **M0.2:** app scaffold, health, CORS, Logfire wiring.
- **M0.3:** Postgres + pgvector + Alembic; SQLAlchemy 2 models for the DESIGN §4 schema.
- **M0.4:** Clerk JWT verification middleware, real `/v1/me`.
- **M1 (this):** projects CRUD, PDF upload + extraction, RAG chat with citations.
- **M2:** risk engine, schedule / budget / RFI parsers, R2 storage, background workers.
