"""Smoke tests for the health + me routers."""

from __future__ import annotations

from fastapi.testclient import TestClient

from pmx_api.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "pmx-api"
    assert "uptime_seconds" in body
    assert body["uptime_seconds"] >= 0


def test_me_returns_stub() -> None:
    response = client.get("/v1/me")
    assert response.status_code == 200
    assert response.json()["authenticated"] is False


def test_openapi_schema_serves() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "PMX AI API"


def test_cors_preflight() -> None:
    response = client.options(
        "/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
