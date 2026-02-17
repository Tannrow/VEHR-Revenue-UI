from __future__ import annotations

import os
import time
from typing import Any

import httpx
from jose import jwt

GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
GITHUB_HTTP_TIMEOUT_SECONDS = 20.0


class GitHubAppAuthError(RuntimeError):
    def __init__(self, detail: str, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class GitHubAppConfigurationError(GitHubAppAuthError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail, status_code=500)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise GitHubAppConfigurationError(f"{name} is not configured")
    return value


def _parse_github_error(response: httpx.Response, body: Any) -> tuple[str, int]:
    detail = f"GitHub API request failed with status {response.status_code}"
    if isinstance(body, dict):
        message = body.get("message")
        if isinstance(message, str) and message.strip():
            detail = message.strip()
    if response.status_code in {400, 401, 403, 404, 409, 422, 429}:
        return detail, response.status_code
    return detail, 502


def load_private_key_pem() -> str:
    path = _required_env("GITHUB_APP_PRIVATE_KEY_PATH")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError as exc:
        raise GitHubAppConfigurationError("GITHUB_APP_PRIVATE_KEY_PATH does not exist") from exc
    except OSError as exc:
        raise GitHubAppConfigurationError("Unable to read GITHUB_APP_PRIVATE_KEY_PATH") from exc


def _parse_app_id(app_id: str | int) -> int:
    if isinstance(app_id, int):
        if app_id <= 0:
            raise GitHubAppConfigurationError("GITHUB_APP_ID must be a positive integer")
        return app_id
    raw = str(app_id).strip()
    if not raw:
        raise GitHubAppConfigurationError("GITHUB_APP_ID must be a positive integer")
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise GitHubAppConfigurationError("GITHUB_APP_ID must be a positive integer") from exc
    if parsed <= 0:
        raise GitHubAppConfigurationError("GITHUB_APP_ID must be a positive integer")
    return parsed


def make_app_jwt(app_id: str | int, private_key_pem: str) -> str:
    now = int(time.time())
    payload = {
        "iat": now - 30,
        "exp": now + 9 * 60,
        "iss": _parse_app_id(app_id),
    }
    try:
        return jwt.encode(payload, private_key_pem, algorithm="RS256")
    except Exception as exc:  # pragma: no cover - relies on jose internals
        raise GitHubAppAuthError("GitHub App JWT signing failed", 500) from exc


def get_installation_token(installation_id: str | int) -> str:
    app_id = _required_env("GITHUB_APP_ID")
    private_key_pem = load_private_key_pem()
    app_jwt = make_app_jwt(app_id, private_key_pem)
    url = f"{GITHUB_API_BASE_URL}/app/installations/{installation_id}/access_tokens"
    try:
        response = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            },
            timeout=GITHUB_HTTP_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise GitHubAppAuthError("GitHub App token request failed", 502) from exc

    body: Any = {}
    try:
        body = response.json()
    except Exception:
        body = {}

    if response.status_code >= 400:
        detail, status_code = _parse_github_error(response, body)
        if status_code == 401:
            detail = "GitHub App authentication failed"
        raise GitHubAppAuthError(detail, status_code)

    token = str(body.get("token", "")).strip()
    if not token:
        raise GitHubAppAuthError("GitHub App token response missing token", 502)
    return token
