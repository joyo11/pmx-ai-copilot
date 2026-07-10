"""Structured logging + tracing via Logfire."""

from __future__ import annotations

import logging

import logfire
from fastapi import FastAPI

from pmx_api.config import Settings


def configure_observability(app: FastAPI, settings: Settings) -> None:
    """Wire Logfire logging. Safe to run without a token (local dev).

    We intentionally do NOT call ``logfire.instrument_fastapi`` here — the current
    opentelemetry-instrumentation-fastapi versions trip on Starlette's
    ``_IncludedRouter`` during CORS preflight. Structured logging still works;
    request-level tracing will land once the version drift is resolved.
    """
    _ = app  # reserved for when instrumentation is re-enabled
    logfire.configure(
        send_to_logfire=settings.logfire_send_to_logfire,
        token=settings.logfire_token,
        service_name="pmx-api",
        environment=settings.environment,
        console=logfire.ConsoleOptions(min_log_level=settings.log_level.lower()),  # type: ignore[arg-type]
    )

    # Route stdlib logging through logfire too.
    logging.basicConfig(
        handlers=[logfire.LogfireLoggingHandler()], level=settings.log_level.upper()
    )
