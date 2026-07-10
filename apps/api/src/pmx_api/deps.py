"""FastAPI request-scoped dependencies.

M0.3 landed the async DB session. M0.4 layered Clerk auth on top. M1 wires
the auth mirror to a real Postgres upsert:

- ``get_db`` / ``DBSession`` — request-scoped :class:`AsyncSession`.
- ``get_current_user`` / ``require_current_user`` — Clerk-authenticated user.

``_mirror_user_to_db`` now performs an idempotent upsert into ``organizations``
and ``users`` on first-touch, using the sync engine (auth is a sync path) so
projects/documents/chat can rely on the FK relationships. It stays a best-effort
side-effect: DB failures log-and-swallow so ``/v1/me`` still works when
Postgres is offline (matches M0.4's tolerance contract).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pmx_api.auth.clerk import (
    ClerkClaims,
    ClerkVerificationError,
    verify_clerk_jwt,
)
from pmx_api.config import Settings, get_settings
from pmx_api.db.session import (
    DatabaseNotConfiguredError,
    get_async_session,
    get_sync_sessionmaker,
)

logger = logging.getLogger(__name__)

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


_DEFAULT_ROLE_FOR_MIRROR = "project_manager"
"""Fallback role when Clerk doesn't hand us an ``org_role`` we recognise.

M0.3's `users.role` CHECK constraint pins the enum. Clerk sends role slugs
like ``org:admin`` / ``org:member`` which don't match — we normalise them
here rather than at query sites. Follow-up: proper role-mapping table.
"""


def _normalise_role(clerk_role: str | None) -> str:
    """Map Clerk org role slugs onto the ``users.role`` enum from DESIGN §4.

    Clerk uses ``org:admin`` / ``org:member`` / custom slugs. Until we ship a
    role-mapping UI we default anyone we don't recognise to ``project_manager``.
    """
    if not clerk_role:
        return _DEFAULT_ROLE_FOR_MIRROR
    tail = clerk_role.split(":")[-1]  # strip "org:" prefix if present
    return (
        tail
        if tail
        in {
            "project_manager",
            "senior_pm",
            "program_manager",
            "construction_manager",
            "executive",
            "owner_rep",
        }
        else _DEFAULT_ROLE_FOR_MIRROR
    )


def _mirror_user_to_db(claims: ClerkClaims) -> None:
    """Upsert the Clerk user + org into ``organizations`` and ``users``.

    Idempotent by design: uses ``ON CONFLICT`` on the natural keys Clerk gives
    us (``clerk_org_id`` / ``clerk_user_id``). Runs on the sync engine because
    ``get_current_user`` is a sync dependency; the write is tiny (two rows)
    and gated on the user actually being present in the request.

    Failures are logged and swallowed. Auth already succeeded at this point —
    the mirror is a "make FKs work" side-effect, not a gate on the response.
    Endpoints that depend on the mirrored row will surface their own error.
    """
    try:
        session_factory = get_sync_sessionmaker()
    except DatabaseNotConfiguredError:
        # No DB configured (e.g. running /v1/me in a local sandbox). Skip.
        return

    # Personal-mode Clerk users have no active org. We synthesise a per-user
    # "personal" org so projects have a valid FK to hang off — one row per
    # signup, invisible in the Clerk dashboard, isolated by construction.
    personal_mode = claims.org_id is None
    org_id = claims.org_id or f"personal_{claims.sub}"

    role = _normalise_role(claims.org_role)
    email = claims.email or f"{claims.sub}@placeholder.pmx"
    org_name = "Personal" if personal_mode else (claims.org_slug or org_id)

    try:
        with session_factory.begin() as session:
            # Upsert the organization first so the users FK resolves.
            session.execute(
                text(
                    """
                    INSERT INTO organizations (clerk_org_id, name)
                    VALUES (:clerk_org_id, :name)
                    ON CONFLICT (clerk_org_id) DO UPDATE
                        SET name = EXCLUDED.name
                    """
                ),
                {"clerk_org_id": org_id, "name": org_name},
            )
            # Upsert the user, resolving org_id via the row we just wrote.
            session.execute(
                text(
                    """
                    INSERT INTO users (clerk_user_id, org_id, email, role)
                    SELECT :clerk_user_id, o.id, :email, :role
                    FROM organizations o
                    WHERE o.clerk_org_id = :clerk_org_id
                    ON CONFLICT (clerk_user_id) DO UPDATE
                        SET org_id = EXCLUDED.org_id,
                            email  = EXCLUDED.email,
                            role   = EXCLUDED.role
                    """
                ),
                {
                    "clerk_user_id": claims.sub,
                    "clerk_org_id": org_id,
                    "email": email,
                    "role": role,
                },
            )
    except SQLAlchemyError as exc:
        # DB blip. Log and move on — auth succeeded, response is still valid.
        logger.warning("Failed to mirror Clerk user %s: %s", claims.sub, exc)


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


# ---------------------------------------------------------------------------
# Tenant resolution
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class TenantContext:
    """Internal UUIDs for the current user + their org.

    ``CurrentUser`` carries Clerk *string* IDs (``user_...``, ``org_...``).
    Everything downstream — projects, documents, chunks, chat sessions — FKs
    against our internal UUIDs. This resolver bridges the two after
    ``_mirror_user_to_db`` has ensured the rows exist.
    """

    user_uuid: str  # UUIDs stringified so mypy stays happy across sync/async
    org_uuid: str


async def resolve_tenant(
    db: AsyncSession,
    current: CurrentUser,
) -> TenantContext:
    """Resolve the current Clerk user into internal ``users.id`` + ``org_id``.

    Personal-mode Clerk users (no active org) are transparently backed by a
    synthetic ``personal_{clerk_user_id}`` org created by ``_mirror_user_to_db``.

    Raises 500 only if the mirror never ran (should be impossible on the auth
    path — surface it clearly instead of a silent NULL FK).
    """
    _ = current.org_id  # kept in signature for future org-scope checks

    row = (
        await db.execute(
            text(
                """
                SELECT u.id AS user_id, u.org_id AS org_id
                FROM users u
                WHERE u.clerk_user_id = :clerk_user_id
                """
            ),
            {"clerk_user_id": current.user_id},
        )
    ).one_or_none()

    if row is None:
        # Mirror hasn't landed (DB was down when auth ran, most likely).
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User mirror missing; retry the request",
        )

    return TenantContext(user_uuid=str(row.user_id), org_uuid=str(row.org_id))
