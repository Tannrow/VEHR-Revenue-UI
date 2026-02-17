from __future__ import annotations

import os
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.integrations.github.app_auth import (
    GITHUB_API_BASE_URL,
    GITHUB_API_VERSION,
    GITHUB_HTTP_TIMEOUT_SECONDS,
    GitHubAppAuthError,
    GitHubAppConfigurationError,
    get_installation_token,
)

router = APIRouter(prefix="/api/dev", tags=["nexus"])


class CodexTaskRequest(BaseModel):
    title: str
    goal: str
    acceptance_criteria: list[str] | None = Field(default=None)
    risk: Literal["low", "med", "high"] = Field(default="low")
    files_or_area: str | None = Field(default=None)
    notes: str | None = Field(default=None)
    requested_by: str | None = Field(default=None)


class CodexTaskResponse(BaseModel):
    status: Literal["started"]
    issue_number: int
    issue_url: str


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


def _build_issue_body(payload: CodexTaskRequest) -> str:
    acceptance = payload.acceptance_criteria or []
    acceptance_block = "\n".join(f"- {item}" for item in acceptance) if acceptance else "- None provided"
    files_block = payload.files_or_area.strip() if payload.files_or_area else "Not specified"
    notes_block = payload.notes.strip() if payload.notes else "None"
    requested_by_block = payload.requested_by.strip() if payload.requested_by else "Not specified"
    constraints_block = "PR only; no secrets; keep changes small."

    return (
        "# Nexus → Codex Task\n\n"
        "## Goal\n"
        f"{payload.goal.strip()}\n\n"
        "## Acceptance Criteria\n"
        f"{acceptance_block}\n\n"
        "## Risk\n"
        f"{payload.risk}\n\n"
        "## Files / Area\n"
        f"{files_block}\n\n"
        "## Constraints\n"
        f"{constraints_block}\n\n"
        "## Notes\n"
        f"{notes_block}\n\n"
        "## Requested By\n"
        f"{requested_by_block}\n"
    )


def _create_issue(*, token: str, payload: CodexTaskRequest) -> dict[str, Any]:
    issue_body = _build_issue_body(payload)
    try:
        response = httpx.post(
            f"{GITHUB_API_BASE_URL}/repos/Tannrow/VEHR/issues",
            headers=_github_headers(token),
            json={
                "title": f"[AI TASK] {payload.title.strip()}",
                "body": issue_body,
                "labels": ["ai-task", f"risk:{payload.risk}"],
            },
            timeout=GITHUB_HTTP_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=500, detail="GitHub issue create request failed") from exc
    body: Any = {}
    try:
        body = response.json()
    except Exception:
        body = {}

    if response.status_code >= 400:
        detail = f"GitHub issue create failed with status {response.status_code}"
        if isinstance(body, dict):
            message = body.get("message")
            if isinstance(message, str) and message.strip():
                detail = message.strip()
        raise HTTPException(status_code=500, detail=detail)

    if not isinstance(body, dict):
        raise HTTPException(status_code=500, detail="Unexpected GitHub issue response format")
    return body


def _dispatch_workflow(*, token: str, issue_number: int, risk: str) -> None:
    try:
        response = httpx.post(
            f"{GITHUB_API_BASE_URL}/repos/Tannrow/VEHR/actions/workflows/codex_task.yml/dispatches",
            headers=_github_headers(token),
            json={
                "ref": "main",
                "inputs": {
                    "issue_number": str(issue_number),
                    "risk": risk,
                },
            },
            timeout=GITHUB_HTTP_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=500, detail="GitHub workflow dispatch request failed") from exc
    if response.status_code != 204:
        raise HTTPException(
            status_code=500,
            detail=f"GitHub workflow dispatch failed with status {response.status_code}",
        )


@router.post("/codex-task", response_model=CodexTaskResponse)
def create_codex_task(payload: CodexTaskRequest) -> CodexTaskResponse:
    try:
        installation_id = os.getenv("GITHUB_APP_INSTALLATION_ID", "").strip()
        if not installation_id:
            raise GitHubAppConfigurationError("GITHUB_APP_INSTALLATION_ID is not configured")
        token = get_installation_token(installation_id)
    except (GitHubAppAuthError, GitHubAppConfigurationError) as exc:
        raise HTTPException(status_code=500, detail=exc.detail) from exc

    issue = _create_issue(token=token, payload=payload)
    issue_number_raw = issue.get("number")
    issue_url = str(issue.get("html_url", "")).strip()
    try:
        issue_number = int(issue_number_raw)
    except Exception:
        raise HTTPException(status_code=500, detail="GitHub issue response missing number")
    if not issue_url:
        raise HTTPException(status_code=500, detail="GitHub issue response missing html_url")

    _dispatch_workflow(token=token, issue_number=issue_number, risk=payload.risk)
    return CodexTaskResponse(status="started", issue_number=issue_number, issue_url=issue_url)
