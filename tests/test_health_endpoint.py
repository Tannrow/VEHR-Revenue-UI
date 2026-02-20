from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_version_endpoint_exposes_commit_and_app_version(monkeypatch) -> None:
    monkeypatch.setenv("COMMIT_SHA", "abc123")
    with TestClient(app) as client:
        response = client.get("/version")

    assert response.status_code == 200
    body = response.json()
    assert body["commit_sha"] == "abc123"
    assert "app_version" in body
