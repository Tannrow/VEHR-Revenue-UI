from __future__ import annotations

import importlib
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
    with pytest.raises(RuntimeError):
        _import_session(monkeypatch, "sqlite:///./invalid.db")
    sys.modules.pop("app.db.session", None)
    _import_session(monkeypatch, "postgresql://user:pass@localhost:5432/okdb")
