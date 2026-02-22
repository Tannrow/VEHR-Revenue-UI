from __future__ import annotations

import importlib
import logging
import os
import sys

import pytest
from fastapi.testclient import TestClient

from app.create_app import create_app


def _unset_env(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    if name in os.environ:
        monkeypatch.delenv(name, raising=False)

def _import_session(monkeypatch: pytest.MonkeyPatch, url: str):
    monkeypatch.setenv("DATABASE_URL", url)
    sys.modules.pop("app.db.session", None)
    importlib.invalidate_caches()
    return importlib.import_module("app.db.session")


def test_startup_skips_when_flag_set(monkeypatch: pytest.MonkeyPatch) -> None:
    _unset_env(monkeypatch, "OPENAI_API_KEY")
    monkeypatch.setenv("SKIP_STARTUP_CHECKS", "1")
    monkeypatch.setenv("TANNER_AI_ENABLED", "1")

    app = create_app(include_router=False)
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200


@pytest.mark.parametrize("enabled_value", [None, "false"])
def test_startup_allows_missing_ringcentral_when_realtime_disabled(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, enabled_value: str | None
) -> None:
    from app.api.v1.endpoints import health as health_endpoints

    class _FakeSession:
        def execute(self, *_args, **_kwargs) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.delenv("SKIP_STARTUP_CHECKS", raising=False)
    monkeypatch.setenv("ENV", "test")
    monkeypatch.delenv("AZURE_DOCINTEL_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_DOCINTEL_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    if enabled_value is None:
        monkeypatch.delenv("RINGCENTRAL_REALTIME_ENABLED", raising=False)
    else:
        monkeypatch.setenv("RINGCENTRAL_REALTIME_ENABLED", enabled_value)
    monkeypatch.delenv("RINGCENTRAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("RINGCENTRAL_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("RINGCENTRAL_SERVER_URL", raising=False)
    monkeypatch.delenv("RINGCENTRAL_REDIRECT_URI", raising=False)
    monkeypatch.setattr(health_endpoints, "SessionLocal", lambda: _FakeSession())
    caplog.set_level(logging.INFO, logger="app.main")

    app = create_app()
    with TestClient(app) as client:
        health_response = client.get("/api/v1/healthz")
        ready_response = client.get("/api/v1/readyz")

    assert health_response.status_code == 200
    assert ready_response.status_code == 200
    assert sum(1 for record in caplog.records if record.message == "ringcentral_realtime_disabled") == 1


def test_startup_fails_when_ringcentral_realtime_enabled_without_client_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SKIP_STARTUP_CHECKS", raising=False)
    monkeypatch.setenv("RINGCENTRAL_REALTIME_ENABLED", "true")
    monkeypatch.delenv("RINGCENTRAL_CLIENT_ID", raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        with TestClient(create_app()):
            pass

    assert "RINGCENTRAL_CLIENT_ID" in str(excinfo.value)


def test_startup_fails_when_tanner_enabled_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _unset_env(monkeypatch, "OPENAI_API_KEY")
    monkeypatch.delenv("SKIP_STARTUP_CHECKS", raising=False)
    monkeypatch.setenv("TANNER_AI_ENABLED", "1")

    app = create_app(include_router=False)
    with pytest.raises(RuntimeError) as excinfo:
        with TestClient(app):
            pass

    assert "OPENAI_API_KEY" in str(excinfo.value)


def test_startup_fails_for_non_postgresql_database(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _import_session(monkeypatch, "sqlite:///./invalid.db")
    with pytest.raises(RuntimeError):
        session._normalize_database_url(os.environ["DATABASE_URL"])
    sys.modules.pop("app.db.session", None)
    session_ok = _import_session(monkeypatch, "postgresql+psycopg://user:pass@localhost:5432/okdb")
    assert session_ok._normalize_database_url(os.environ["DATABASE_URL"]).startswith("postgresql+psycopg://")


@pytest.mark.parametrize(
    "url",
    [
        "postgres://user:pass@localhost:5432/okdb",
        "postgresql://user:pass@localhost:5432/okdb",
        "postgresql+psycopg://user:pass@localhost:5432/okdb",
    ],
)
def test_startup_normalizes_postgres_urls(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    session = _import_session(monkeypatch, url)
    normalized = session._normalize_database_url(os.environ["DATABASE_URL"])
    assert normalized.startswith("postgresql+psycopg://")
