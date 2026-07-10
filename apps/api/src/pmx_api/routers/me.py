"""Current user endpoint (Clerk-backed as of M0.4).

Design decision (DESIGN.md §5): `/v1/me` is intentionally tolerant of missing
auth. Instead of 401, it returns 200 with `{authenticated: false}` so the
frontend can call it unconditionally on every page load — including the
landing page — without dealing with error handling on the happy path.

If a valid Bearer token is present, the response includes the Clerk user id,
active org id, and role. Endpoints that must reject anonymous callers should
use `pmx_api.deps.require_current_user` instead.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from pmx_api.deps import CurrentUser, get_current_user

router = APIRouter(tags=["me"])


class MeResponse(BaseModel):
    authenticated: bool
    user_id: str | None = None
    org_id: str | None = None
    role: str | None = None
    email: str | None = None


@router.get(
    "/v1/me",
    response_model=MeResponse,
    summary="Current user (tolerant of missing auth)",
)
def me(
    user: Annotated[CurrentUser | None, Depends(get_current_user)],
) -> MeResponse:
    """Return the current authenticated user, or a stub for anonymous callers.

    Returns 200 in both cases; callers switch on `authenticated`.
    """
    if user is None:
        return MeResponse(authenticated=False)
    return MeResponse(
        authenticated=True,
        user_id=user.user_id,
        org_id=user.org_id,
        role=user.role,
        email=user.email,
    )
