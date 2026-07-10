"""FastAPI request-scoped dependencies.

M0.3 landed the async DB session. M0.4 layered Clerk auth on top. This file
now exposes both:

- ``get_db`` / ``DBSession`` — request-scoped :class:`AsyncSession`.
- ``get_current_user`` / ``require_current_user`` — Clerk-authenticated user.

The DB-mirror hook for Clerk users lives in ``_mirror_user_to_db`` and stays
a no-op until we wire the real upsert against the ``users`` / ``organizations``
tables. Kept intentionally decoupled so ``/v1/me`` works off raw Clerk claims
even when Postgres is offline.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pmx_api.auth.clerk import (
    ClerkClaims,
    ClerkVerificationError,
    verify_clerk_jwt,
)
from pmx_api.config import Settings, get_settings
from pmx_api.db.session import get_async_session

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped :class:`AsyncSession`."""
    async for session in get_async_session():
        yield session


DBSession = Annotated[AsyncSession, Depends(get_db)]
"""Type alias for injecting an async DB session into a route handler."""


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class CurrentUser:
    """The identity we hand to routers after auth.

    ``org_id`` and ``role`` reflect the *active* Clerk org context; they can be
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

    Placeholder until we wire the real upsert against the ``users`` and
    ``organizations`` models from M0.3. Kept as a separate function so a
    follow-up PR can drop the SQL in without touching auth flow.
    """
    _ = claims  # will feed the upsert


def get_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser | None:
    """Return the current Clerk-authenticated user, or None if no token.

    We do NOT raise 401 when the header is missing — some endpoints (notably
    ``/v1/me``) intentionally return a ``{authenticated: false}`` payload for
    unauthenticated callers. Callers that require auth should check for None
    and raise 401 themselves, or use ``require_current_user`` below.
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
    """Same as ``get_current_user``, but 401s on missing token instead of None.

    Use this on endpoints that must not be reachable anonymously.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
