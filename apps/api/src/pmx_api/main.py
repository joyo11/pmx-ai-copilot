"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pmx_api.config import get_settings
from pmx_api.observability import configure_observability
from pmx_api.routers import health, me


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hooks. DB pool + Redis wire in later milestones."""
    del app  # reserved for M0.3+
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="PMX AI API",
        description="Backend for the PMX AI Project Risk Copilot.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(me.router)

    # Instrumentation runs last, after all routes are mounted, otherwise
    # OpenTelemetry's route walker trips on `_IncludedRouter`.
    configure_observability(app, settings)

    return app


app = create_app()


def main() -> None:
    """CLI entry: `uv run pmx-api` for a local dev server."""
    import uvicorn

    uvicorn.run(
        "pmx_api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
