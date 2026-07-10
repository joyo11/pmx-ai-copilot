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

## Project layout

```
apps/api/
├── pyproject.toml
├── uv.lock
├── .python-version
├── .env.example
├── src/pmx_api/
│   ├── __init__.py
│   ├── main.py           # FastAPI factory + CLI entry
│   ├── config.py         # Pydantic Settings
│   ├── observability.py  # Logfire wiring
│   └── routers/
│       ├── health.py     # GET /v1/health
│       └── me.py         # GET /v1/me (stub until M0.4 auth)
└── tests/
    └── test_health.py
```

## Endpoints (M0.2)

| Method | Path              | Purpose                             |
|--------|-------------------|-------------------------------------|
| GET    | `/v1/health`      | Liveness probe with uptime seconds  |
| GET    | `/v1/me`          | Auth stub (real impl in M0.4)       |
| GET    | `/docs`           | Interactive OpenAPI docs            |
| GET    | `/openapi.json`   | Machine-readable schema             |

## Milestones

- **M0.2 (this):** app scaffold, health, CORS, Logfire wiring.
- **M0.3:** Postgres + pgvector + Alembic.
- **M0.4:** Clerk JWT verification middleware, real `/v1/me`.
- **M1:** projects CRUD, uploads, extraction, risk engine, chat.
