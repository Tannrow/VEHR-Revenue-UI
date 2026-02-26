from __future__ import annotations

import asyncio
import importlib
import logging

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

import app.main as app_main
from app.main import app, get_cors_origins


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


def test_wildcard_cors_allowed_origins_falls_back_to_localhost_defaults(monkeypatch) -> None:
    monkeypatch.delenv("LOCAL_DEV", raising=False)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    origins = get_cors_origins()
    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins
    assert "*" not in origins


def _reload_main_with_env(monkeypatch, *, cors_allowed_origins: str | None, cors_origin_regex: str | None):
    if cors_allowed_origins is None:
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", cors_allowed_origins)

    if cors_origin_regex is None:
        monkeypatch.delenv("CORS_ORIGIN_REGEX", raising=False)
    else:
        monkeypatch.setenv("CORS_ORIGIN_REGEX", cors_origin_regex)

    monkeypatch.delenv("LOCAL_DEV", raising=False)
    return importlib.reload(app_main)


def test_cors_preflight_disallowed_random_aca_fqdn_returns_400(monkeypatch) -> None:
    main_module = _reload_main_with_env(
        monkeypatch,
        cors_allowed_origins="http://localhost:3000",
        cors_origin_regex=None,
    )
    with TestClient(main_module.app) as client:
        response = client.options(
            "/api/v1/auth/me",
            headers=_preflight_headers(origin="https://tenant-12345.aca.example.com"),
        )
    assert response.status_code == 400
    assert response.headers.get("access-control-allow-origin") is None


def test_cors_preflight_allowed_regex_matched_aca_fqdn_returns_204(monkeypatch) -> None:
    main_module = _reload_main_with_env(
        monkeypatch,
        cors_allowed_origins="http://localhost:3000",
        cors_origin_regex=r"^https://[a-z0-9-]+\.aca\.example\.com$",
    )
    with TestClient(main_module.app) as client:
        origin = "https://tenant-12345.aca.example.com"
        response = client.options(
            "/api/v1/auth/me",
            headers=_preflight_headers(origin=origin),
        )
    assert response.status_code in (200, 204)
    assert response.headers.get("access-control-allow-origin") == origin


def test_cors_preflight_malformed_regex_never_allows_origin(monkeypatch) -> None:
    main_module = _reload_main_with_env(
        monkeypatch,
        cors_allowed_origins="http://localhost:3000",
        cors_origin_regex=r"([invalid",
    )
    with TestClient(main_module.app) as client:
        response = client.options(
            "/api/v1/auth/me",
            headers=_preflight_headers(origin="https://tenant-12345.aca.example.com"),
        )
    assert response.status_code == 400
    assert response.headers.get("access-control-allow-origin") is None

