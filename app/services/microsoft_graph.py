import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.integration_account import IntegrationAccount
from app.services.integration_tokens import TokenEncryptionError, decrypt_token, encrypt_token

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
DEFAULT_GRAPH_SCOPES = "openid profile email offline_access User.Read Sites.Read.All Files.ReadWrite.All"
GRAPH_TIMEOUT_SECONDS = 20.0
GRAPH_DOWNLOAD_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class SharePointSite:
    id: str
    name: str
    web_url: str


@dataclass(frozen=True)
class SharePointDrive:
    id: str
    name: str
    web_url: str


@dataclass(frozen=True)
class SharePointItem:
    id: str
    name: str
    is_folder: bool
    size: int | None
    web_url: str
    last_modified: str | None
    mime_type: str | None


@dataclass(frozen=True)
class SharePointDownloadPayload:
    stream: Iterator[bytes]
    filename: str
    content_type: str
    content_length: int | None
    web_url: str | None


@dataclass
class _CachedAccessToken:
    access_token: str
    expires_at: datetime


class MicrosoftGraphServiceError(RuntimeError):
    def __init__(self, detail: str, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class MicrosoftIntegrationNotConnectedError(MicrosoftGraphServiceError):
    def __init__(self) -> None:
        super().__init__("Microsoft integration is not connected for this user", status_code=409)


class MicrosoftGraphConfigurationError(MicrosoftGraphServiceError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail, status_code=500)


_ACCESS_TOKEN_CACHE: dict[str, _CachedAccessToken] = {}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise MicrosoftGraphConfigurationError(f"{name} is not configured")
    return value


def _graph_scopes() -> str:
    return os.getenv("MS_GRAPH_SCOPES", "").strip() or DEFAULT_GRAPH_SCOPES


def _integration_account_for_user(*, db: Session, organization_id: str, user_id: str) -> IntegrationAccount:
    account = (
        db.execute(
            select(IntegrationAccount)
            .where(
                IntegrationAccount.organization_id == organization_id,
                IntegrationAccount.user_id == user_id,
                IntegrationAccount.provider == "microsoft",
                IntegrationAccount.revoked_at.is_(None),
            )
            .order_by(IntegrationAccount.updated_at.desc())
        )
        .scalars()
        .first()
    )
    if not account:
        raise MicrosoftIntegrationNotConnectedError()
    return account


def _cached_access_token(*, account_id: str) -> str | None:
    cached = _ACCESS_TOKEN_CACHE.get(account_id)
    if not cached:
        return None
    if cached.expires_at <= _now_utc():
        _ACCESS_TOKEN_CACHE.pop(account_id, None)
        return None
    return cached.access_token


def _cache_access_token(*, account_id: str, access_token: str, expires_in_seconds: int) -> None:
    ttl_seconds = max(expires_in_seconds - 60, 30)
    _ACCESS_TOKEN_CACHE[account_id] = _CachedAccessToken(
        access_token=access_token,
        expires_at=_now_utc() + timedelta(seconds=ttl_seconds),
    )


def _token_refresh_payload(*, refresh_token: str) -> dict[str, str]:
    return {
        "client_id": _required_env("MS_CLIENT_ID"),
        "client_secret": _required_env("MS_CLIENT_SECRET"),
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": _graph_scopes(),
    }


def _parse_graph_error(response: httpx.Response, body: Any) -> tuple[str, int]:
    detail = f"Microsoft Graph request failed with status {response.status_code}"
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

    if response.status_code in {400, 401, 403, 404, 409}:
        return detail, response.status_code
    return detail, 502


def _refresh_access_token(*, db: Session, account: IntegrationAccount) -> str:
    try:
        refresh_token = decrypt_token(account.refresh_token_enc)
    except TokenEncryptionError as exc:
        raise MicrosoftGraphServiceError("Stored Microsoft token could not be decrypted", 500) from exc

    try:
        response = httpx.post(
            MICROSOFT_TOKEN_URL,
            data=_token_refresh_payload(refresh_token=refresh_token),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=GRAPH_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise MicrosoftGraphServiceError("Microsoft token refresh request failed", 502) from exc

    body: dict[str, Any] = {}
    try:
        body = response.json()
    except Exception:
        body = {}

    if response.status_code >= 400:
        detail, status_code = _parse_graph_error(response, body)
        raise MicrosoftGraphServiceError(detail, status_code)

    access_token = str(body.get("access_token", "")).strip()
    if not access_token:
        raise MicrosoftGraphServiceError("Microsoft token response missing access_token", 502)

    expires_in_raw = body.get("expires_in", 3600)
    try:
        expires_in_seconds = int(expires_in_raw)
    except Exception:
        expires_in_seconds = 3600

    rotated_refresh_token = str(body.get("refresh_token", "")).strip()
    if rotated_refresh_token:
        try:
            account.refresh_token_enc = encrypt_token(rotated_refresh_token)
            db.add(account)
            db.commit()
        except TokenEncryptionError as exc:
            db.rollback()
            raise MicrosoftGraphServiceError("Unable to encrypt rotated Microsoft token", 500) from exc

    _cache_access_token(
        account_id=account.id,
        access_token=access_token,
        expires_in_seconds=expires_in_seconds,
    )
    return access_token


def _access_token_for_user(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    force_refresh: bool = False,
) -> tuple[str, IntegrationAccount]:
    account = _integration_account_for_user(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
    )

    if not force_refresh:
        cached = _cached_access_token(account_id=account.id)
        if cached:
            return cached, account

    return _refresh_access_token(db=db, account=account), account


def _graph_get_json(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    path: str,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    target_url = f"{GRAPH_BASE_URL}/{path.lstrip('/')}"

    for attempt in range(2):
        access_token, account = _access_token_for_user(
            db=db,
            organization_id=organization_id,
            user_id=user_id,
            force_refresh=attempt > 0,
        )
        try:
            response = httpx.get(
                target_url,
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
                timeout=GRAPH_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise MicrosoftGraphServiceError("Microsoft Graph request failed", 502) from exc

        if response.status_code == 401 and attempt == 0:
            _ACCESS_TOKEN_CACHE.pop(account.id, None)
            continue

        body: Any = {}
        try:
            body = response.json()
        except Exception:
            body = {}

        if response.status_code >= 400:
            detail, status_code = _parse_graph_error(response, body)
            raise MicrosoftGraphServiceError(detail, status_code)

        if not isinstance(body, dict):
            raise MicrosoftGraphServiceError("Unexpected Microsoft Graph response format", 502)
        return body

    raise MicrosoftGraphServiceError("Microsoft Graph authorization failed", 401)


def get_microsoft_graph_profile(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
) -> dict[str, str | None]:
    body = _graph_get_json(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        path="me",
        params={"$select": "displayName,userPrincipalName"},
    )
    return {
        "displayName": str(body.get("displayName", "")).strip() or None,
        "userPrincipalName": str(body.get("userPrincipalName", "")).strip() or None,
    }


def search_sharepoint_sites(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    search: str,
) -> list[SharePointSite]:
    search_value = search.strip()
    if not search_value:
        return []

    body = _graph_get_json(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        path="sites",
        params={"search": search_value},
    )
    rows = body.get("value", [])
    if not isinstance(rows, list):
        return []

    sites: list[SharePointSite] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        site_id = str(row.get("id", "")).strip()
        if not site_id:
            continue
        sites.append(
            SharePointSite(
                id=site_id,
                name=str(row.get("name", "")).strip() or "Untitled Site",
                web_url=str(row.get("webUrl", "")).strip(),
            )
        )
    return sites


def list_sharepoint_drives(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    site_id: str,
) -> list[SharePointDrive]:
    body = _graph_get_json(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        path=f"sites/{site_id}/drives",
    )
    rows = body.get("value", [])
    if not isinstance(rows, list):
        return []

    drives: list[SharePointDrive] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        drive_id = str(row.get("id", "")).strip()
        if not drive_id:
            continue
        drives.append(
            SharePointDrive(
                id=drive_id,
                name=str(row.get("name", "")).strip() or "Untitled Drive",
                web_url=str(row.get("webUrl", "")).strip(),
            )
        )
    return drives


def _map_sharepoint_item(row: dict[str, Any]) -> SharePointItem | None:
    item_id = str(row.get("id", "")).strip()
    if not item_id:
        return None

    size_value = row.get("size")
    size: int | None = None
    try:
        if size_value is not None:
            size = int(size_value)
    except Exception:
        size = None

    file_info = row.get("file")
    mime_type: str | None = None
    if isinstance(file_info, dict):
        mime_raw = file_info.get("mimeType")
        if isinstance(mime_raw, str):
            mime_type = mime_raw.strip() or None

    return SharePointItem(
        id=item_id,
        name=str(row.get("name", "")).strip() or "Untitled",
        is_folder=bool(row.get("folder")),
        size=size,
        web_url=str(row.get("webUrl", "")).strip(),
        last_modified=str(row.get("lastModifiedDateTime", "")).strip() or None,
        mime_type=mime_type,
    )


def list_sharepoint_children(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    drive_id: str,
    item_id: str | None = None,
) -> list[SharePointItem]:
    path = (
        f"drives/{drive_id}/items/{item_id}/children"
        if item_id
        else f"drives/{drive_id}/root/children"
    )
    body = _graph_get_json(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        path=path,
    )
    rows = body.get("value", [])
    if not isinstance(rows, list):
        return []

    items: list[SharePointItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        mapped = _map_sharepoint_item(row)
        if mapped:
            items.append(mapped)
    return items


def _stream_from_url(url: str) -> Iterator[bytes]:
    with httpx.stream("GET", url, timeout=GRAPH_DOWNLOAD_TIMEOUT_SECONDS) as response:
        if response.status_code >= 400:
            raise MicrosoftGraphServiceError("SharePoint download request failed", 502)
        for chunk in response.iter_bytes():
            if chunk:
                yield chunk


def _stream_from_graph_content(*, url: str, access_token: str) -> Iterator[bytes]:
    with httpx.stream(
        "GET",
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=GRAPH_DOWNLOAD_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as response:
        if response.status_code >= 400:
            detail, status_code = _parse_graph_error(response, {})
            raise MicrosoftGraphServiceError(detail, status_code)
        for chunk in response.iter_bytes():
            if chunk:
                yield chunk


def get_sharepoint_item_download(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    drive_id: str,
    item_id: str,
) -> SharePointDownloadPayload:
    metadata = _graph_get_json(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        path=f"drives/{drive_id}/items/{item_id}",
        params={"$select": "id,name,size,webUrl,file,@microsoft.graph.downloadUrl"},
    )

    name = str(metadata.get("name", "")).strip() or "download.bin"
    size_value = metadata.get("size")
    content_length: int | None = None
    try:
        if size_value is not None:
            content_length = int(size_value)
    except Exception:
        content_length = None

    content_type = "application/octet-stream"
    file_value = metadata.get("file")
    if isinstance(file_value, dict):
        mime_type = file_value.get("mimeType")
        if isinstance(mime_type, str) and mime_type.strip():
            content_type = mime_type.strip()

    web_url = str(metadata.get("webUrl", "")).strip() or None
    download_url = metadata.get("@microsoft.graph.downloadUrl")
    if isinstance(download_url, str) and download_url.strip():
        return SharePointDownloadPayload(
            stream=_stream_from_url(download_url.strip()),
            filename=name,
            content_type=content_type,
            content_length=content_length,
            web_url=web_url,
        )

    access_token, _account = _access_token_for_user(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        force_refresh=False,
    )
    return SharePointDownloadPayload(
        stream=_stream_from_graph_content(
            url=f"{GRAPH_BASE_URL}/drives/{drive_id}/items/{item_id}/content",
            access_token=access_token,
        ),
        filename=name,
        content_type=content_type,
        content_length=content_length,
        web_url=web_url,
    )
