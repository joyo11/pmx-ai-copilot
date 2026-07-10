"""Current user echo. Real Clerk-backed identity lands in M0.4."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["me"])


class MeResponse(BaseModel):
    authenticated: bool = False
    note: str = "Clerk auth ships in M0.4. This endpoint currently returns a stub."


@router.get("/v1/me", response_model=MeResponse, summary="Current user (stub until M0.4)")
def me() -> MeResponse:
    return MeResponse()
