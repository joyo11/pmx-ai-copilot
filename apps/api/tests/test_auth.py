"""Tests for M0.4 Clerk auth: /v1/me tolerance, JWT verification, JWKS caching.

We generate a real RS256 keypair per test module, serve it as a JWKS document
via a `httpx.get` monkeypatch, and sign tokens with the matching private key.
That exercises the real PyJWT + `cryptography` verification path without any
network I/O.
"""

from __future__ import annotations

import base64
import time
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from pmx_api.auth import clerk as clerk_auth
from pmx_api.config import get_settings
from pmx_api.main import app

_TEST_ISSUER = "https://test-instance.clerk.accounts.dev"
_TEST_KID = "test-kid-1"


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


@pytest.fixture(scope="module")
def jwks_document(rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]) -> dict[str, Any]:
    _, public = rsa_keypair
    numbers = public.public_numbers()

    def _b64(value: int) -> str:
        # RFC 7518 base64url without padding
        byte_length = (value.bit_length() + 7) // 8
        raw = value.to_bytes(byte_length, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return {
        "keys": [
            {
                "kty": "RSA",
                "kid": _TEST_KID,
                "use": "sig",
                "alg": "RS256",
                "n": _b64(numbers.n),
                "e": _b64(numbers.e),
            }
        ]
    }


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    """Reset the JWKS cache + Settings cache between tests."""
    clerk_auth._clear_jwks_cache()
    get_settings.cache_clear()
    yield
    clerk_auth._clear_jwks_cache()
    get_settings.cache_clear()


@pytest.fixture
def configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLERK_JWT_ISSUER", _TEST_ISSUER)
    monkeypatch.delenv("CLERK_JWT_AUDIENCE", raising=False)
    get_settings.cache_clear()


@pytest.fixture
def signed_token(rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]) -> str:
    private, _ = rsa_keypair
    now = int(time.time())
    payload = {
        "sub": "user_test_123",
        "iss": _TEST_ISSUER,
        "iat": now,
        "exp": now + 300,
        "org_id": "org_test_abc",
        "org_role": "org:admin",
        "org_slug": "acme",
        "email": "pm@example.com",
    }
    pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return jwt.encode(payload, pem, algorithm="RS256", headers={"kid": _TEST_KID})


def _make_jwks_response(document: dict[str, Any]) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = document
    response.raise_for_status.return_value = None
    return response


# --------------------------------------------------------------------------- #
# /v1/me — anonymous                                                          #
# --------------------------------------------------------------------------- #


def test_me_without_token_returns_200_and_authenticated_false() -> None:
    client = TestClient(app)
    response = client.get("/v1/me")

    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is False
    assert body["user_id"] is None
    assert body["org_id"] is None
    assert body["role"] is None


# --------------------------------------------------------------------------- #
# /v1/me — authenticated                                                      #
# --------------------------------------------------------------------------- #


def test_me_with_valid_token_returns_user_info(
    configured_env: None,
    signed_token: str,
    jwks_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del configured_env  # signals monkeypatch is applied

    call_count = 0

    def _fake_get(url: str, timeout: float = 5.0) -> MagicMock:
        nonlocal call_count
        call_count += 1
        assert url.endswith("/.well-known/jwks.json")
        return _make_jwks_response(jwks_document)

    monkeypatch.setattr(clerk_auth.httpx, "get", _fake_get)

    client = TestClient(app)
    response = client.get(
        "/v1/me",
        headers={"Authorization": f"Bearer {signed_token}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["authenticated"] is True
    assert body["user_id"] == "user_test_123"
    assert body["org_id"] == "org_test_abc"
    assert body["role"] == "org:admin"
    assert body["email"] == "pm@example.com"


# --------------------------------------------------------------------------- #
# /v1/me — invalid tokens                                                     #
# --------------------------------------------------------------------------- #


def test_me_with_expired_token_returns_401(
    configured_env: None,
    rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    jwks_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del configured_env
    private, _ = rsa_keypair
    now = int(time.time())
    expired_payload = {
        "sub": "user_expired",
        "iss": _TEST_ISSUER,
        "iat": now - 3600,
        "exp": now - 60,
    }
    pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    expired = jwt.encode(expired_payload, pem, algorithm="RS256", headers={"kid": _TEST_KID})

    monkeypatch.setattr(
        clerk_auth.httpx,
        "get",
        lambda url, timeout=5.0: _make_jwks_response(jwks_document),
    )

    client = TestClient(app)
    response = client.get("/v1/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_me_with_garbage_token_returns_401(
    configured_env: None,
    jwks_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del configured_env
    monkeypatch.setattr(
        clerk_auth.httpx,
        "get",
        lambda url, timeout=5.0: _make_jwks_response(jwks_document),
    )
    client = TestClient(app)
    response = client.get("/v1/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# JWKS caching                                                                #
# --------------------------------------------------------------------------- #


def test_jwks_is_cached_across_requests(
    configured_env: None,
    signed_token: str,
    jwks_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """N /v1/me hits should trigger exactly one JWKS fetch."""
    del configured_env
    call_count = 0

    def _fake_get(url: str, timeout: float = 5.0) -> MagicMock:
        nonlocal call_count
        call_count += 1
        return _make_jwks_response(jwks_document)

    monkeypatch.setattr(clerk_auth.httpx, "get", _fake_get)

    client = TestClient(app)
    for _ in range(5):
        response = client.get(
            "/v1/me",
            headers={"Authorization": f"Bearer {signed_token}"},
        )
        assert response.status_code == 200

    assert call_count == 1, f"Expected 1 JWKS fetch, got {call_count}"


def test_missing_issuer_config_returns_500(
    monkeypatch: pytest.MonkeyPatch, signed_token: str
) -> None:
    """Server-side misconfiguration surfaces as 500, not a silent auth pass."""
    monkeypatch.delenv("CLERK_JWT_ISSUER", raising=False)
    get_settings.cache_clear()

    client = TestClient(app)
    response = client.get(
        "/v1/me",
        headers={"Authorization": f"Bearer {signed_token}"},
    )
    assert response.status_code == 500
