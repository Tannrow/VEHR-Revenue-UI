from __future__ import annotations

import asyncio
import logging

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.main import app


ALLOWED_ORIGIN = "http://localhost:3000"
EXPECTED_METHODS = {"GET", "POST", "PATCH", "DELETE", "OPTIONS"}
TARGET_PATHS = [
    "/api/v1/auth/login",
    "/api/v1/auth/me",
    "/api/v1/ai/notifications/stream",
]


def _preflight_headers(origin: str = ALLOWED_ORIGIN) -> dict[str, str]:
    return {
        "Origin": origin,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization,Content-Type",
    }


def _assert_preflight_headers(response) -> None:
    assert response.status_code in (200, 204)
    assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN
    assert response.headers.get("access-control-allow-credentials") == "true"

    allow_methods = {m.strip() for m in response.headers.get("access-control-allow-methods", "").split(",") if m.strip()}
    assert EXPECTED_METHODS.issubset(allow_methods)


def test_cors_preflight_for_protected_endpoints_testclient(caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.main")
    with TestClient(app) as client:
        for path in TARGET_PATHS:
            response = client.options(path, headers=_preflight_headers())
            _assert_preflight_headers(response)

    success_logs = [rec.message for rec in caplog.records if "cors_preflight_success" in rec.message]
    assert len(success_logs) >= len(TARGET_PATHS)


def test_cors_preflight_failure_logs_for_disallowed_origin(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="app.main")
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/auth/me",
            headers=_preflight_headers(origin="https://evil.example.com"),
        )

    assert response.status_code == 400
    assert response.headers.get("access-control-allow-origin") is None
    assert any("cors_preflight_failure" in rec.message for rec in caplog.records)


def test_cors_preflight_for_protected_endpoints_asyncclient() -> None:
    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            for path in TARGET_PATHS:
                response = await client.options(path, headers=_preflight_headers())
                _assert_preflight_headers(response)

    asyncio.run(_run())

