from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

PBI_TOKEN_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
PBI_API_BASE_URL = "https://api.powerbi.com/v1.0/myorg"
PBI_HTTP_TIMEOUT_SECONDS = 20.0


class PowerBIServiceError(RuntimeError):
    def __init__(self, detail: str, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class PowerBIConfigurationError(PowerBIServiceError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail, status_code=500)


@dataclass(frozen=True)
class PowerBIAppCredentials:
    tenant_id: str
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class PowerBIEmbedToken:
    token: str
    expires_on: str


@dataclass(frozen=True)
class PowerBIReport:
    id: str
    name: str
    embed_url: str
    dataset_id: str | None = None


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise PowerBIConfigurationError(f"{name} is not configured")
    return value


def load_powerbi_app_credentials() -> PowerBIAppCredentials:
    return PowerBIAppCredentials(
        tenant_id=_required_env("PBI_TENANT_ID"),
        client_id=_required_env("PBI_CLIENT_ID"),
        client_secret=_required_env("PBI_CLIENT_SECRET"),
    )


def _parse_error_detail(*, response: httpx.Response, body: Any) -> tuple[str, int]:
    detail = f"Power BI request failed with status {response.status_code}"
    if isinstance(body, dict):
        error_value = body.get("error")
        if isinstance(error_value, dict):
            code = str(error_value.get("code", "")).strip()
            message = str(error_value.get("message", "")).strip()
            if code and message:
                detail = f"{code}: {message}"
            elif message:
                detail = message
        elif isinstance(error_value, str) and error_value.strip():
            detail = error_value.strip()
        elif isinstance(body.get("message"), str) and body["message"].strip():
            detail = body["message"].strip()

    if response.status_code in {400, 401, 403, 404, 409, 429}:
        return detail, response.status_code
    return detail, 502


class PowerBIClient:
    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        timeout_seconds: float = PBI_HTTP_TIMEOUT_SECONDS,
    ) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> PowerBIClient:
        creds = load_powerbi_app_credentials()
        return cls(
            tenant_id=creds.tenant_id,
            client_id=creds.client_id,
            client_secret=creds.client_secret,
        )

    def get_access_token(self) -> str:
        token_url = f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": PBI_TOKEN_SCOPE,
        }
        try:
            response = httpx.post(
                token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self._timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise PowerBIServiceError("Power BI token request failed", 502) from exc

        body: Any = {}
        try:
            body = response.json()
        except Exception:
            body = {}

        if response.status_code >= 400:
            detail, status_code = _parse_error_detail(response=response, body=body)
            raise PowerBIServiceError(detail, status_code)

        access_token = str(body.get("access_token", "")).strip()
        if not access_token:
            raise PowerBIServiceError("Power BI token response missing access_token", 502)
        return access_token

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        access_token: str,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{PBI_API_BASE_URL}/{path.lstrip('/')}"
        try:
            response = httpx.request(
                method,
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                params=params,
                json=json_body,
                timeout=self._timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise PowerBIServiceError("Power BI API request failed", 502) from exc

        body: Any = {}
        try:
            body = response.json()
        except Exception:
            body = {}

        if response.status_code >= 400:
            detail, status_code = _parse_error_detail(response=response, body=body)
            raise PowerBIServiceError(detail, status_code)

        if not isinstance(body, dict):
            raise PowerBIServiceError("Unexpected Power BI response format", 502)
        return body

    def list_workspaces(self, *, access_token: str) -> list[dict[str, Any]]:
        body = self._request_json(method="GET", path="groups", access_token=access_token)
        rows = body.get("value", [])
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def list_reports(self, *, workspace_id: str, access_token: str) -> list[dict[str, Any]]:
        body = self._request_json(
            method="GET",
            path=f"groups/{workspace_id}/reports",
            access_token=access_token,
        )
        rows = body.get("value", [])
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def list_datasets(self, *, workspace_id: str, access_token: str) -> list[dict[str, Any]]:
        body = self._request_json(
            method="GET",
            path=f"groups/{workspace_id}/datasets",
            access_token=access_token,
        )
        rows = body.get("value", [])
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def get_report(self, *, workspace_id: str, report_id: str, access_token: str) -> PowerBIReport:
        body = self._request_json(
            method="GET",
            path=f"groups/{workspace_id}/reports/{report_id}",
            access_token=access_token,
        )
        resolved_report_id = str(body.get("id", "")).strip() or report_id
        embed_url = str(body.get("embedUrl", "")).strip()
        if not embed_url:
            raise PowerBIServiceError("Power BI report embedUrl is missing", 502)
        return PowerBIReport(
            id=resolved_report_id,
            name=str(body.get("name", "")).strip() or resolved_report_id,
            embed_url=embed_url,
            dataset_id=str(body.get("datasetId", "")).strip() or None,
        )

    def generate_report_embed_token(
        self,
        *,
        workspace_id: str,
        report_id: str,
        dataset_id: str,
        username: str,
        rls_role: str,
        access_token: str,
    ) -> PowerBIEmbedToken:
        body = self._request_json(
            method="POST",
            path=f"groups/{workspace_id}/reports/{report_id}/GenerateToken",
            access_token=access_token,
            json_body={
                "accessLevel": "View",
                "identities": [
                    {
                        "username": username,
                        "roles": [rls_role],
                        "datasets": [dataset_id],
                    }
                ],
            },
        )

        token_value = str(body.get("token", "")).strip()
        expires_on = str(body.get("expiration", "")).strip()
        if not token_value:
            raise PowerBIServiceError("Power BI embed token response missing token", 502)
        if not expires_on:
            raise PowerBIServiceError("Power BI embed token response missing expiration", 502)
        return PowerBIEmbedToken(token=token_value, expires_on=expires_on)
