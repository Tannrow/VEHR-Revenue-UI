import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.integration_account import IntegrationAccount
from app.db.models.user_microsoft_connection import UserMicrosoftConnection
from app.services.graph_client import (
    MicrosoftGraphClientError,
    MicrosoftGraphNotConnectedError,
    acquire_graph_token,
)
from app.services.integration_tokens import TokenEncryptionError, decrypt_token, encrypt_token

logger = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
DEFAULT_GRAPH_SCOPES = "openid profile email offline_access User.Read Sites.Read.All Files.ReadWrite.All"
GRAPH_TIMEOUT_SECONDS = 20.0
GRAPH_DOWNLOAD_TIMEOUT_SECONDS = 60.0
GRAPH_CACHE_TTL_SECONDS = 600

DEFAULT_ALLOWED_SHAREPOINT_SITE_URL = (
    "https://valleyhealthandcounseling.sharepoint.com/sites/ValleyHealthHomePage"
)

ALLOWED_SHAREPOINT_DOMAIN = "sharepoint.com"


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
class SharePointWorkspace:
    site: SharePointSite
    drives: list[SharePointDrive]


@dataclass(frozen=True)
class SharePointItemPreview:
    id: str
    name: str
    web_url: str
    mime_type: str | None
    preview_kind: str
    is_previewable: bool
    preview_url: str | None
    download_url: str | None


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


@dataclass
class _CachedSite:
    site: SharePointSite
    expires_at: datetime


@dataclass
class _CachedString:
    value: str
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
_ALLOWED_SITE_CACHE: dict[str, _CachedSite] = {}
_DRIVE_SITE_CACHE: dict[str, _CachedString] = {}
_ITEM_DRIVE_CACHE: dict[str, _CachedString] = {}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _cache_expiry() -> datetime:
    return _now_utc() + timedelta(seconds=GRAPH_CACHE_TTL_SECONDS)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise MicrosoftGraphConfigurationError(f"{name} is not configured")
    return value


def _graph_scopes() -> str:
    return os.getenv("MS_GRAPH_SCOPES", "").strip() or DEFAULT_GRAPH_SCOPES


def _normalize_scopes_list(scopes: list[str] | None) -> list[str]:
    if scopes is None:
        scopes = [item.strip() for item in _graph_scopes().split() if item.strip()]
    ordered: list[str] = []
    for scope in scopes:
        normalized = str(scope or "").strip()
        if not normalized or normalized in ordered:
            continue
        ordered.append(normalized)
    return ordered


def _access_token_cache_key(*, account_id: str, scopes: list[str]) -> str:
    # Scope-aware cache to avoid reusing a token missing Tasks/Calendars permissions for assistant flows.
    normalized_scopes = " ".join(sorted(scopes))
    return f"{account_id}:{normalized_scopes}"


def _normalize_host(host: str) -> str:
    return host.strip().lower().rstrip(".")


def _is_allowed_sharepoint_host(host: str) -> bool:
    return _normalize_host(host).endswith(f".{ALLOWED_SHAREPOINT_DOMAIN}")


def _validate_sharepoint_site_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    if parsed.scheme != "https":
        raise MicrosoftGraphConfigurationError("SHAREPOINT_ALLOWED_SITE_URL must use https")
    if not parsed.hostname:
        raise MicrosoftGraphConfigurationError("SHAREPOINT_ALLOWED_SITE_URL must include a hostname")
    if not _is_allowed_sharepoint_host(parsed.hostname):
        raise MicrosoftGraphConfigurationError("SHAREPOINT_ALLOWED_SITE_URL must be a sharepoint.com domain")
    if not parsed.path or parsed.path == "/":
        raise MicrosoftGraphConfigurationError("SHAREPOINT_ALLOWED_SITE_URL must include the site path")
    return raw_url.strip()


def _allowed_site_reference() -> tuple[str | None, str]:
    configured_id = os.getenv("SHAREPOINT_ALLOWED_SITE_ID", "").strip() or None
    configured_url = os.getenv("SHAREPOINT_ALLOWED_SITE_URL", "").strip() or DEFAULT_ALLOWED_SHAREPOINT_SITE_URL
    return configured_id, _validate_sharepoint_site_url(configured_url)


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


def _cached_access_token(*, account_id: str, scopes: list[str]) -> str | None:
    cache_key = _access_token_cache_key(account_id=account_id, scopes=scopes)
    cached = _ACCESS_TOKEN_CACHE.get(cache_key)
    if not cached:
        return None
    if cached.expires_at <= _now_utc():
        _ACCESS_TOKEN_CACHE.pop(cache_key, None)
        return None
    return cached.access_token


def _cache_access_token(*, account_id: str, scopes: list[str], access_token: str, expires_in_seconds: int) -> None:
    ttl_seconds = max(expires_in_seconds - 60, 30)
    cache_key = _access_token_cache_key(account_id=account_id, scopes=scopes)
    _ACCESS_TOKEN_CACHE[cache_key] = _CachedAccessToken(
        access_token=access_token,
        expires_at=_now_utc() + timedelta(seconds=ttl_seconds),
    )


def _token_refresh_payload(*, refresh_token: str, scopes: list[str]) -> dict[str, str]:
    return {
        "client_id": _required_env("MS_CLIENT_ID"),
        "client_secret": _required_env("MS_CLIENT_SECRET"),
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": " ".join(scopes),
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


def _refresh_access_token(*, db: Session, account: IntegrationAccount, scopes: list[str]) -> tuple[str, datetime | None]:
    try:
        refresh_token = decrypt_token(account.refresh_token_enc)
    except TokenEncryptionError as exc:
        raise MicrosoftGraphServiceError("Stored Microsoft token could not be decrypted", 500) from exc

    try:
        response = httpx.post(
            MICROSOFT_TOKEN_URL,
            data=_token_refresh_payload(refresh_token=refresh_token, scopes=scopes),
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
    expires_at = _now_utc() + timedelta(seconds=max(expires_in_seconds, 0))

    rotated_refresh_token = str(body.get("refresh_token", "")).strip()
    if rotated_refresh_token:
        try:
            account.refresh_token_enc = encrypt_token(rotated_refresh_token)
            db.add(account)
            db.commit()
            connection = _microsoft_connection_for_user(
                db=db,
                organization_id=account.organization_id,
                user_id=account.user_id,
            )
            if connection is not None:
                connection.refresh_token_enc = account.refresh_token_enc
                db.add(connection)
                db.commit()
        except TokenEncryptionError as exc:
            db.rollback()
            raise MicrosoftGraphServiceError("Unable to encrypt rotated Microsoft token", 500) from exc

    _cache_access_token(
        account_id=account.id,
        scopes=scopes,
        access_token=access_token,
        expires_in_seconds=expires_in_seconds,
    )
    return access_token, expires_at


def _access_token_for_user(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    scopes: list[str] | None = None,
    force_refresh: bool = False,
) -> tuple[str, IntegrationAccount]:
    normalized_scopes = _normalize_scopes_list(scopes)
    account = _integration_account_for_user(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
    )

    if not force_refresh:
        cached = _cached_access_token(account_id=account.id, scopes=normalized_scopes)
        if cached:
            return cached, account

    # Prefer MSAL token cache when available, but fall back to refresh-token flow.
    try:
        access_token = acquire_graph_token(
            db=db,
            organization_id=organization_id,
            user_id=user_id,
            scopes=normalized_scopes or None,
            force_refresh=force_refresh,
        )
        _cache_access_token(
            account_id=account.id,
            scopes=normalized_scopes,
            access_token=access_token,
            expires_in_seconds=3600,
        )
        return access_token, account
    except MicrosoftGraphNotConnectedError:
        pass
    except MicrosoftGraphClientError as exc:
        logger.warning("Microsoft Graph MSAL token acquisition failed: %s", exc.detail)

    access_token, _expires_at = _refresh_access_token(db=db, account=account, scopes=normalized_scopes)
    return access_token, account


def _graph_request_json(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    method: str,
    path: str,
    scopes: list[str] | None = None,
    params: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_url = f"{GRAPH_BASE_URL}/{path.lstrip('/')}"
    normalized_scopes = _normalize_scopes_list(scopes)

    for attempt in range(2):
        access_token, account = _access_token_for_user(
            db=db,
            organization_id=organization_id,
            user_id=user_id,
            scopes=normalized_scopes,
            force_refresh=attempt > 0,
        )
        try:
            response = httpx.request(
                method,
                target_url,
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
                json=json_body,
                timeout=GRAPH_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise MicrosoftGraphServiceError("Microsoft Graph request failed", 502) from exc

        if response.status_code == 401 and attempt == 0:
            _ACCESS_TOKEN_CACHE.pop(
                _access_token_cache_key(account_id=account.id, scopes=normalized_scopes),
                None,
            )
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


def _graph_get_json(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    path: str,
    scopes: list[str] | None = None,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    return _graph_request_json(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        method="GET",
        path=path,
        scopes=scopes,
        params=params,
    )


def _graph_post_json(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    path: str,
    scopes: list[str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _graph_request_json(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        method="POST",
        path=path,
        scopes=scopes,
        json_body=body,
    )


def _site_from_row(row: dict[str, Any]) -> SharePointSite:
    site_id = str(row.get("id", "")).strip()
    if not site_id:
        raise MicrosoftGraphServiceError("Allowed SharePoint site id could not be resolved", 500)

    web_url = str(row.get("webUrl", "")).strip()
    if not web_url:
        raise MicrosoftGraphServiceError("Allowed SharePoint site URL could not be resolved", 500)

    return SharePointSite(
        id=site_id,
        name=str(row.get("name", "")).strip() or "Valley Health Home Page",
        web_url=web_url,
    )


def _allowed_site_cache_key(organization_id: str) -> str:
    configured_id, configured_url = _allowed_site_reference()
    return f"{organization_id}:{configured_id or configured_url}"


def _resolve_allowed_site(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
) -> SharePointSite:
    cache_key = _allowed_site_cache_key(organization_id)
    cached = _ALLOWED_SITE_CACHE.get(cache_key)
    if cached and cached.expires_at > _now_utc():
        return cached.site

    configured_id, configured_url = _allowed_site_reference()
    if configured_id:
        row = _graph_get_json(
            db=db,
            organization_id=organization_id,
            user_id=user_id,
            path=f"sites/{configured_id}",
            params={"$select": "id,name,webUrl"},
        )
        site = _site_from_row(row)
    else:
        parsed = urlparse(configured_url)
        hostname = parsed.hostname or ""
        path = parsed.path.rstrip("/")
        lookup_path = f"sites/{hostname}:{path}"
        row = _graph_get_json(
            db=db,
            organization_id=organization_id,
            user_id=user_id,
            path=lookup_path,
            params={"$select": "id,name,webUrl"},
        )
        site = _site_from_row(row)

    _ALLOWED_SITE_CACHE[cache_key] = _CachedSite(site=site, expires_at=_cache_expiry())
    return site


def _drive_site_cache_key(*, organization_id: str, drive_id: str) -> str:
    return f"{organization_id}:{drive_id}"


def _item_drive_cache_key(*, organization_id: str, item_id: str) -> str:
    return f"{organization_id}:{item_id}"


def _cache_drive_site(*, organization_id: str, drive_id: str, site_id: str) -> None:
    _DRIVE_SITE_CACHE[_drive_site_cache_key(organization_id=organization_id, drive_id=drive_id)] = _CachedString(
        value=site_id,
        expires_at=_cache_expiry(),
    )


def _cached_drive_site(*, organization_id: str, drive_id: str) -> str | None:
    cache_key = _drive_site_cache_key(organization_id=organization_id, drive_id=drive_id)
    cached = _DRIVE_SITE_CACHE.get(cache_key)
    if not cached:
        return None
    if cached.expires_at <= _now_utc():
        _DRIVE_SITE_CACHE.pop(cache_key, None)
        return None
    return cached.value


def _cache_item_drive(*, organization_id: str, item_id: str, drive_id: str) -> None:
    _ITEM_DRIVE_CACHE[_item_drive_cache_key(organization_id=organization_id, item_id=item_id)] = _CachedString(
        value=drive_id,
        expires_at=_cache_expiry(),
    )


def _cached_item_drive(*, organization_id: str, item_id: str) -> str | None:
    cache_key = _item_drive_cache_key(organization_id=organization_id, item_id=item_id)
    cached = _ITEM_DRIVE_CACHE.get(cache_key)
    if not cached:
        return None
    if cached.expires_at <= _now_utc():
        _ITEM_DRIVE_CACHE.pop(cache_key, None)
        return None
    return cached.value


def _ensure_drive_in_allowed_site(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    drive_id: str,
) -> SharePointSite:
    allowed_site = _resolve_allowed_site(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
    )
    cached_site_id = _cached_drive_site(organization_id=organization_id, drive_id=drive_id)
    if cached_site_id == allowed_site.id:
        return allowed_site

    body = _graph_get_json(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        path=f"sites/{allowed_site.id}/drives",
    )
    rows = body.get("value", [])
    if not isinstance(rows, list):
        rows = []

    allowed_drive_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        mapped = _map_sharepoint_drive(row)
        if not mapped:
            continue
        allowed_drive_ids.add(mapped.id)
        _cache_drive_site(
            organization_id=organization_id,
            drive_id=mapped.id,
            site_id=allowed_site.id,
        )

    if drive_id not in allowed_drive_ids:
        raise MicrosoftGraphServiceError(
            "Access denied: requested drive is outside the allowed SharePoint workspace",
            403,
        )
    return allowed_site


def _resolve_item_drive_id(
    *,
    organization_id: str,
    item_id: str,
    drive_id: str | None,
) -> str:
    if drive_id and drive_id.strip():
        _cache_item_drive(
            organization_id=organization_id,
            item_id=item_id,
            drive_id=drive_id.strip(),
        )
        return drive_id.strip()

    cached = _cached_item_drive(organization_id=organization_id, item_id=item_id)
    if cached:
        return cached

    raise MicrosoftGraphServiceError(
        "Drive context is required for this item. Refresh the folder listing and retry.",
        400,
    )


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


def _map_sharepoint_drive(row: dict[str, Any]) -> SharePointDrive | None:
    drive_id = str(row.get("id", "")).strip()
    if not drive_id:
        return None
    return SharePointDrive(
        id=drive_id,
        name=str(row.get("name", "")).strip() or "Untitled Drive",
        web_url=str(row.get("webUrl", "")).strip(),
    )


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


def get_sharepoint_workspace(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
) -> SharePointWorkspace:
    allowed_site = _resolve_allowed_site(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
    )
    body = _graph_get_json(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        path=f"sites/{allowed_site.id}/drives",
    )
    rows = body.get("value", [])
    if not isinstance(rows, list):
        rows = []

    drives: list[SharePointDrive] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        drive = _map_sharepoint_drive(row)
        if not drive:
            continue
        _cache_drive_site(
            organization_id=organization_id,
            drive_id=drive.id,
            site_id=allowed_site.id,
        )
        drives.append(drive)

    return SharePointWorkspace(site=allowed_site, drives=drives)


def list_sharepoint_drive_items(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    drive_id: str,
    parent_id: str,
) -> list[SharePointItem]:
    _ensure_drive_in_allowed_site(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        drive_id=drive_id,
    )

    normalized_parent = parent_id.strip()
    path = (
        f"drives/{drive_id}/root/children"
        if normalized_parent.lower() == "root"
        else f"drives/{drive_id}/items/{normalized_parent}/children"
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
            _cache_item_drive(
                organization_id=organization_id,
                item_id=mapped.id,
                drive_id=drive_id,
            )
            items.append(mapped)
    return items


def get_sharepoint_item_metadata(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    item_id: str,
    drive_id: str | None = None,
) -> SharePointItem:
    resolved_drive_id = _resolve_item_drive_id(
        organization_id=organization_id,
        item_id=item_id,
        drive_id=drive_id,
    )
    _ensure_drive_in_allowed_site(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        drive_id=resolved_drive_id,
    )
    body = _graph_get_json(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        path=f"drives/{resolved_drive_id}/items/{item_id}",
        params={"$select": "id,name,size,webUrl,lastModifiedDateTime,file,folder,parentReference"},
    )
    mapped = _map_sharepoint_item(body)
    if not mapped:
        raise MicrosoftGraphServiceError("SharePoint item not found", 404)

    parent_reference = body.get("parentReference")
    if isinstance(parent_reference, dict):
        parent_drive_id = str(parent_reference.get("driveId", "")).strip()
        if parent_drive_id and parent_drive_id != resolved_drive_id:
            raise MicrosoftGraphServiceError(
                "Access denied: requested item is outside the allowed SharePoint workspace",
                403,
            )

    _cache_item_drive(
        organization_id=organization_id,
        item_id=item_id,
        drive_id=resolved_drive_id,
    )
    return mapped


def get_sharepoint_item_preview(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    item_id: str,
    drive_id: str | None = None,
) -> SharePointItemPreview:
    resolved_drive_id = _resolve_item_drive_id(
        organization_id=organization_id,
        item_id=item_id,
        drive_id=drive_id,
    )
    item = get_sharepoint_item_metadata(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        item_id=item_id,
        drive_id=resolved_drive_id,
    )
    if item.is_folder:
        raise MicrosoftGraphServiceError("Folders do not support preview", 400)

    mime = (item.mime_type or "").lower()
    is_pdf = mime == "application/pdf" or item.name.lower().endswith(".pdf")
    is_image = mime.startswith("image/")
    preview_kind = "pdf" if is_pdf else "image" if is_image else "external"

    preview_url: str | None = None
    if not is_pdf and not is_image:
        try:
            preview_body = _graph_post_json(
                db=db,
                organization_id=organization_id,
                user_id=user_id,
                path=f"drives/{resolved_drive_id}/items/{item_id}/preview",
                body={"allowEdit": False},
            )
            preview_url_raw = preview_body.get("getUrl")
            if isinstance(preview_url_raw, str) and preview_url_raw.strip():
                preview_url = preview_url_raw.strip()
        except MicrosoftGraphServiceError:
            preview_url = None

    download_url = (
        f"/api/v1/integrations/microsoft/sharepoint/items/{item_id}/download?driveId={resolved_drive_id}"
        if is_pdf or is_image
        else None
    )
    return SharePointItemPreview(
        id=item.id,
        name=item.name,
        web_url=item.web_url,
        mime_type=item.mime_type,
        preview_kind=preview_kind,
        is_previewable=is_pdf or is_image,
        preview_url=preview_url,
        download_url=download_url,
    )


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


def get_sharepoint_item_download_by_item(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    item_id: str,
    drive_id: str | None = None,
) -> SharePointDownloadPayload:
    resolved_drive_id = _resolve_item_drive_id(
        organization_id=organization_id,
        item_id=item_id,
        drive_id=drive_id,
    )
    return get_sharepoint_item_download(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        drive_id=resolved_drive_id,
        item_id=item_id,
    )


def get_sharepoint_item_download(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    drive_id: str,
    item_id: str,
) -> SharePointDownloadPayload:
    _ensure_drive_in_allowed_site(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        drive_id=drive_id,
    )

    metadata = _graph_get_json(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        path=f"drives/{drive_id}/items/{item_id}",
        params={"$select": "id,name,size,webUrl,file,@microsoft.graph.downloadUrl,parentReference"},
    )

    parent_reference = metadata.get("parentReference")
    if isinstance(parent_reference, dict):
        parent_drive_id = str(parent_reference.get("driveId", "")).strip()
        if parent_drive_id and parent_drive_id != drive_id:
            raise MicrosoftGraphServiceError(
                "Access denied: requested item is outside the allowed SharePoint workspace",
                403,
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
    _cache_item_drive(
        organization_id=organization_id,
        item_id=item_id,
        drive_id=drive_id,
    )

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


_ASSISTANT_REMINDER_GRAPH_SCOPES = [
    "User.Read",
    "Tasks.ReadWrite",
    "Calendars.ReadWrite",
]


def _microsoft_connection_for_user(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
) -> UserMicrosoftConnection | None:
    return db.execute(
        select(UserMicrosoftConnection).where(
            UserMicrosoftConnection.organization_id == organization_id,
            UserMicrosoftConnection.user_id == user_id,
            UserMicrosoftConnection.revoked_at.is_(None),
        )
    ).scalar_one_or_none()


def _persist_connection_tokens(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    access_token: str,
    expires_at: datetime | None,
    refresh_token_enc: str | None = None,
) -> None:
    if not access_token:
        return
    connection = _microsoft_connection_for_user(db=db, organization_id=organization_id, user_id=user_id)
    if connection is None:
        return
    try:
        connection.access_token_enc = encrypt_token(access_token)
    except TokenEncryptionError:
        logger.warning("Microsoft Graph access token encryption failed for org=%s user=%s", organization_id, user_id)
        return
    if refresh_token_enc:
        connection.refresh_token_enc = refresh_token_enc
    connection.expires_at = expires_at
    db.add(connection)
    db.commit()


def _resolve_or_create_todo_list_id(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    list_name: str,
) -> str:
    connection = _microsoft_connection_for_user(db=db, organization_id=organization_id, user_id=user_id)
    cached_list_id = str(connection.todo_list_id).strip() if connection and connection.todo_list_id else ""
    if cached_list_id:
        return cached_list_id

    body = _graph_get_json(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        path="me/todo/lists",
        scopes=_ASSISTANT_REMINDER_GRAPH_SCOPES,
        params={"$top": "100"},
    )
    rows = body.get("value", [])
    if not isinstance(rows, list):
        rows = []

    resolved_id: str | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        display_name = str(row.get("displayName", "")).strip()
        if display_name != list_name:
            continue
        list_id = str(row.get("id", "")).strip()
        if list_id:
            resolved_id = list_id
            break

    if resolved_id is None:
        created = _graph_post_json(
            db=db,
            organization_id=organization_id,
            user_id=user_id,
            path="me/todo/lists",
            scopes=_ASSISTANT_REMINDER_GRAPH_SCOPES,
            body={"displayName": list_name},
        )
        resolved_id = str(created.get("id", "")).strip() or None

    if not resolved_id:
        raise MicrosoftGraphServiceError("Microsoft Graph To Do list create response missing id", 502)

    if connection is not None:
        connection.todo_list_id = resolved_id
        db.add(connection)
        db.commit()

    return resolved_id


def create_todo_task_draft(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    list_name: str,
    title: str,
    body: str,
    due_datetime: str,
    time_zone: str,
) -> str:
    list_id = _resolve_or_create_todo_list_id(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        list_name=list_name,
    )

    task_payload: dict[str, Any] = {
        "title": title,
        "body": {"contentType": "text", "content": body},
        "dueDateTime": {"dateTime": due_datetime, "timeZone": time_zone},
    }

    try:
        created = _graph_post_json(
            db=db,
            organization_id=organization_id,
            user_id=user_id,
            path=f"me/todo/lists/{list_id}/tasks",
            scopes=_ASSISTANT_REMINDER_GRAPH_SCOPES,
            body=task_payload,
        )
    except MicrosoftGraphServiceError as exc:
        # Clear cached list id if it was deleted/renamed and retry once.
        if exc.status_code == 404:
            connection = _microsoft_connection_for_user(db=db, organization_id=organization_id, user_id=user_id)
            if connection is not None and connection.todo_list_id:
                connection.todo_list_id = None
                db.add(connection)
                db.commit()
            list_id = _resolve_or_create_todo_list_id(
                db=db,
                organization_id=organization_id,
                user_id=user_id,
                list_name=list_name,
            )
            created = _graph_post_json(
                db=db,
                organization_id=organization_id,
                user_id=user_id,
                path=f"me/todo/lists/{list_id}/tasks",
                scopes=_ASSISTANT_REMINDER_GRAPH_SCOPES,
                body=task_payload,
            )
        else:
            raise

    task_id = str(created.get("id", "")).strip()
    if not task_id:
        raise MicrosoftGraphServiceError("Microsoft Graph To Do task create response missing id", 502)
    return task_id


def create_outlook_event_draft(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    subject: str,
    body: str,
    start_datetime: str,
    end_datetime: str,
    time_zone: str,
    transaction_id: str | None = None,
) -> str:
    event_payload: dict[str, Any] = {
        "subject": subject,
        "body": {"contentType": "text", "content": body},
        "start": {"dateTime": start_datetime, "timeZone": time_zone},
        "end": {"dateTime": end_datetime, "timeZone": time_zone},
    }
    if transaction_id:
        event_payload["transactionId"] = transaction_id

    created = _graph_post_json(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        path="me/events",
        scopes=_ASSISTANT_REMINDER_GRAPH_SCOPES,
        body=event_payload,
    )
    event_id = str(created.get("id", "")).strip()
    if not event_id:
        raise MicrosoftGraphServiceError("Microsoft Graph event create response missing id", 502)
    return event_id


def refresh_microsoft_connection_tokens(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    scopes: list[str] | None = None,
) -> datetime | None:
    normalized_scopes = _normalize_scopes_list(scopes or _ASSISTANT_REMINDER_GRAPH_SCOPES)
    account = _integration_account_for_user(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
    )
    access_token, expires_at = _refresh_access_token(db=db, account=account, scopes=normalized_scopes)
    _persist_connection_tokens(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        access_token=access_token,
        expires_at=expires_at,
        refresh_token_enc=account.refresh_token_enc,
    )
    return expires_at
