"""Liveness + readiness."""

from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from pmx_api.config import get_settings

router = APIRouter(tags=["health"])

_STARTED_AT = time.time()


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "pmx-api"
    environment: str
    uptime_seconds: float


@router.get("/v1/health", response_model=HealthResponse, summary="Liveness probe")
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        environment=settings.environment,
        uptime_seconds=round(time.time() - _STARTED_AT, 3),
    )
