"""FastAPI dependencies.

Notes on M0.3 (Postgres) not being merged here:
    Any DB writes triggered by auth (e.g. mirroring the Clerk user + org into
    our `users` / `organizations` tables per DESIGN.md §4) are wrapped in a
    `try/except ImportError` so this file loads even when the DB layer does
    not exist yet. Once M0.3 merges, the `_mirror_user_to_db` branch starts
    doing real inserts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from pmx_api.auth.clerk import (
    ClerkClaims,
    ClerkVerificationError,
    verify_clerk_jwt,
)
from pmx_api.config import Settings, get_settings


@dataclass(slots=True, frozen=True)
class CurrentUser:
    """The identity we hand to routers after auth.

    `org_id` and `role` reflect the *active* Clerk org context; they can be
    None for personal-mode users (no active org).
    """

    user_id: str
    org_id: str | None
    role: str | None
    email: str | None


def _extract_bearer_token(request: Request) -> str | None:
    # Starlette's Headers are case-insensitive.
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def _mirror_user_to_db(claims: ClerkClaims) -> None:
    """Upsert the Clerk user + org into our Postgres tables.

    Guarded against M0.3 (DB layer) not being merged into this branch yet.
    Once `pmx_api.db` exists with a `Session` factory + `users`/`organizations`
    models, replace the placeholder inside the try-block with a real upsert.
    """
    try:
        # Deferred import so this file loads without the DB package present.
        # M0.3 lands `pmx_api.db` with a Session factory + user/org models.
        import importlib

        importlib.import_module("pmx_api.db")
    except ImportError:
        # M0.3 not merged yet — skip the mirror silently. `/v1/me` still works
        # off the raw Clerk claims.
        return

    # M0.3 present: real upsert lands here. Kept minimal on purpose so a
    # merge in M0.3 can drop in without touching M0.4 shape.
    _ = claims


def get_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser | None:
    """Return the current Clerk-authenticated user, or None if no token.

    We do NOT raise 401 when the header is missing — some endpoints (notably
    `/v1/me`) intentionally return a `{authenticated: false}` payload for
    unauthenticated callers. Callers that require auth should check for None
    and raise 401 themselves, or use `require_current_user` below.
    """
    token = _extract_bearer_token(request)
    if token is None:
        return None

    issuer = settings.clerk_jwt_issuer
    if not issuer:
        # Misconfigured server, not a client error. Fail loudly.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CLERK_JWT_ISSUER is not configured",
        )

    try:
        claims = verify_clerk_jwt(
            token,
            issuer=issuer,
            audience=settings.clerk_jwt_audience,
        )
    except ClerkVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    _mirror_user_to_db(claims)

    return CurrentUser(
        user_id=claims.sub,
        org_id=claims.org_id,
        role=claims.org_role,
        email=claims.email,
    )


def require_current_user(
    user: Annotated[CurrentUser | None, Depends(get_current_user)],
) -> CurrentUser:
    """Same as `get_current_user`, but 401s on missing token instead of None.

    Use this on endpoints that must not be reachable anonymously.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
