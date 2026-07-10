"""Clerk JWT verification.

Clerk signs session JWTs with a per-instance RS256 key. The public keys are
served from `{issuer}/.well-known/jwks.json`. We fetch them once, cache them
for an hour (`cachetools.TTLCache`), and use PyJWT + `cryptography` to verify
the signature + standard claims (iss, exp, nbf).

Design notes:
- We do NOT hit Clerk's `/session` endpoint. JWT verification is fully offline
  after JWKS fetch, which keeps `/v1/me` cheap on the hot path.
- Audience is only enforced if `CLERK_JWT_AUDIENCE` is configured. Clerk's
  default session tokens do not have an `aud` claim, so this stays opt-in.
- The cache is process-local. That's fine for a single-worker Render deploy in
  M0.4; if we scale to multiple workers, each still caches independently and
  refetches once per hour.
"""

from __future__ import annotations

from typing import Any, cast

import httpx
import jwt
from cachetools import TTLCache
from jwt import PyJWKSet
from pydantic import BaseModel, Field, ValidationError

_JWKS_CACHE_TTL_SECONDS = 3600  # 1 hour
_JWKS_CACHE_MAXSIZE = 8  # one entry per issuer; tiny by design

# Module-level cache. Keyed by JWKS URL.
_jwks_cache: TTLCache[str, dict[str, Any]] = TTLCache(
    maxsize=_JWKS_CACHE_MAXSIZE, ttl=_JWKS_CACHE_TTL_SECONDS
)


class ClerkVerificationError(Exception):
    """Raised when a Clerk JWT cannot be verified."""


class ClerkClaims(BaseModel):
    """Subset of Clerk session claims we rely on.

    Clerk's docs: https://clerk.com/docs/backend-requests/resources/session-tokens
    """

    sub: str = Field(description="Clerk user id (user_...)")
    org_id: str | None = Field(default=None, description="Active org id (org_...)")
    org_role: str | None = Field(default=None, description="Role in the active org")
    org_slug: str | None = Field(default=None, description="Slug of active org")
    email: str | None = Field(default=None)
    exp: int
    iat: int
    iss: str


def _jwks_url_for(issuer: str) -> str:
    return f"{issuer.rstrip('/')}/.well-known/jwks.json"


def _get_jwks(jwks_url: str) -> dict[str, Any]:
    """Return the JWKS document, fetching + caching if missing/stale.

    The cache is a `TTLCache(ttl=1h)`. On miss, we do a synchronous
    `httpx.get`. Tests can patch `httpx.get` to assert single-fetch behavior.
    """
    cached = _jwks_cache.get(jwks_url)
    if cached is not None:
        return cached

    response = httpx.get(jwks_url, timeout=5.0)
    response.raise_for_status()
    jwks = cast(dict[str, Any], response.json())
    _jwks_cache[jwks_url] = jwks
    return jwks


def _clear_jwks_cache() -> None:
    """Test helper — reset the process-local JWKS cache."""
    _jwks_cache.clear()


def _signing_key(token: str, jwks: dict[str, Any]) -> Any:
    """Resolve the RSA public key that signed this token.

    Uses PyJWT's own `PyJWKSet` for kid matching so key-format edge cases stay
    on the library side. Returns the underlying `cryptography` key object,
    which `jwt.decode` accepts directly.
    """
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")
    if kid is None:
        raise ClerkVerificationError("Token header missing 'kid'")

    jwk_set = PyJWKSet.from_dict(jwks)
    for pyjwk in jwk_set.keys:
        if pyjwk.key_id == kid:
            return pyjwk.key
    raise ClerkVerificationError(f"No JWK matches kid={kid!r}")


def verify_clerk_jwt(
    token: str,
    *,
    issuer: str,
    audience: str | None = None,
) -> ClerkClaims:
    """Verify a Clerk-issued JWT and return typed claims.

    Raises:
        ClerkVerificationError: token is malformed, expired, wrong issuer,
            wrong audience, or signed by an unknown key.
    """
    if not issuer:
        raise ClerkVerificationError("CLERK_JWT_ISSUER is not configured")

    jwks_url = _jwks_url_for(issuer)
    try:
        jwks = _get_jwks(jwks_url)
    except httpx.HTTPError as exc:
        raise ClerkVerificationError(f"Could not fetch JWKS: {exc}") from exc

    try:
        # We resolve the signing key from the cached JWKS ourselves rather than
        # constructing `PyJWKClient(jwks_url)`, which would issue its own HTTP
        # request and bypass our TTLCache.
        key = _signing_key(token, jwks)
    except ClerkVerificationError:
        raise
    except (jwt.exceptions.InvalidKeyError, jwt.exceptions.DecodeError) as exc:
        raise ClerkVerificationError(f"Could not resolve signing key: {exc}") from exc

    options: dict[str, Any] = {"require": ["exp", "iat", "iss", "sub"]}
    decode_kwargs: dict[str, Any] = {
        "algorithms": ["RS256"],
        "issuer": issuer,
        "options": options,
    }
    if audience is not None:
        decode_kwargs["audience"] = audience
    else:
        # Clerk's default session token has no `aud` — skip audience checking.
        options["verify_aud"] = False

    try:
        payload = jwt.decode(token, key, **decode_kwargs)
    except jwt.ExpiredSignatureError as exc:
        raise ClerkVerificationError("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise ClerkVerificationError(f"Invalid token: {exc}") from exc

    try:
        return ClerkClaims.model_validate(payload)
    except ValidationError as exc:
        raise ClerkVerificationError(f"Claims failed validation: {exc}") from exc
