from fastapi.testclient import TestClient
import pytest

from app.main import create_app
import app.api.v1.endpoints.nexus_codex as nexus_codex


class FakeHTTPX:
    def __init__(self):
        self.posts = []

    def post(self, url, *args, **kwargs):
        self.posts.append({"url": url, "json": kwargs.get("json")})

        class Resp:
            def __init__(self, url):
                # GitHub: issue create = 201, dispatch = 204
                self.status_code = 204 if "/dispatches" in url else 201

            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "number": 123,
                    "html_url": "https://github.com/org/repo/issues/123",
                }

            @property
            def text(self):
                return ""

        return Resp(url)


def test_dispatch_inputs_match_workflow_contract(monkeypatch):
    app = create_app(enable_startup_validation=False)
    client = TestClient(app)

    monkeypatch.setattr(nexus_codex, "get_installation_token", lambda *_a, **_k: "test-token")

    fake = FakeHTTPX()
    monkeypatch.setattr(nexus_codex, "httpx", fake)

    resp = client.post(
        "/api/v1/api/dev/codex-task",
        json={"title": "Test", "goal": "Check dispatch inputs"},
    )

    assert resp.status_code in (200, 201), resp.text

    dispatch_calls = [p for p in fake.posts if "/dispatches" in p["url"]]
    assert dispatch_calls, "No workflow dispatch call captured"

    inputs = dispatch_calls[0]["json"]["inputs"]

    # Hard contract: must match workflow exactly
    assert set(inputs.keys()) == {"issue_number", "risk", "retry_count"}, inputs
    assert inputs["issue_number"] not in (None, "")
    assert inputs["retry_count"] == "0"
