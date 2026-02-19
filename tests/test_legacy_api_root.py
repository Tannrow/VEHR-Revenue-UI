from fastapi.testclient import TestClient

from app.main import app


def test_legacy_api_root_get_and_post() -> None:
    with TestClient(app) as client:
        for path in ("/api", "/api/"):
            for method in ("get", "post"):
                response = getattr(client, method)(path)
                assert response.status_code == 200
                assert response.json() == {
                    "deprecated": True,
                    "message": "Use /api/v1/* endpoints. This endpoint will be removed.",
                    "replacement": "/api/v1",
                }
