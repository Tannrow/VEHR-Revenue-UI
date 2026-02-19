import base64
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import msal
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse, StreamingResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, require_permission
from app.core.security import JWT_ALGORITHM, JWT_SECRET
from app.db.models.integration_account import IntegrationAccount
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.user_microsoft_connection import UserMicrosoftConnection
from app.db.session import get_db
from app.services.audit import log_event
from app.services.integration_tokens import TokenEncryptionError, encrypt_token
from app.services.microsoft_graph import (
    MicrosoftGraphServiceError,
    get_microsoft_graph_profile,
    refresh_microsoft_connection_tokens,
    get_sharepoint_item_download_by_item,
    get_sharepoint_item_preview,
    get_sharepoint_workspace,
    list_sharepoint_drive_items,
)


router = APIRouter(tags=["Integrations"])
logger = logging.getLogger(__name__)

MICROSOFT_AUTHORIZE_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
STATE_TTL_MINUTES = 10
DEFAULT_GRAPH_SCOPES = "openid profile email offline_access User.Read Sites.Read.All Files.ReadWrite.All"
DEFAULT_POST_CONNECT_REDIRECT = "https://360-encompass.com/admin/integrations/microsoft"
STATE_TOKEN_TYPE = "microsoft_oauth_state"


class MicrosoftOAuthConfigError(RuntimeError):
    pass


class MicrosoftConnectResponse(BaseModel):
    authorization_url: str


class MicrosoftConnectionTestResponse(BaseModel):
    display_name: str | None = None
    user_principal_name: str | None = None


class MicrosoftDisconnectResponse(BaseModel):
    status: str


class MicrosoftRefreshResponse(BaseModel):
    status: str
    expires_at: datetime | None = None


class SharePointSiteRead(BaseModel):
    id: str
    name: str
    web_url: str


class SharePointDriveRead(BaseModel):
    id: str
    name: str
    web_url: str


class SharePointWorkspaceRead(BaseModel):
    site: SharePointSiteRead
    drives: list[SharePointDriveRead]


class SharePointItemRead(BaseModel):
    id: str
    name: str
    is_folder: bool
    size: int | None = None
    web_url: str
    last_modified_date_time: str | None = None
    mime_type: str | None = None


class SharePointItemPreviewRead(BaseModel):
    id: str
    name: str
    web_url: str
    mime_type: str | None = None
    preview_kind: str
    is_previewable: bool
    preview_url: str | None = None
    download_url: str | None = None


def _sanitize_reason(raw_reason: str) -> str:
    normalized = "".join(
        ch if ch.isalnum() or ch == "_" else "_"
        for ch in raw_reason.strip().lower()
    )
    compact = "_".join(part for part in normalized.split("_") if part)
    return compact[:80] or "unknown_error"


def _state_signing_secret() -> str:
    return os.getenv("STATE_SIGNING_KEY", "").strip() or JWT_SECRET


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise MicrosoftOAuthConfigError(f"{name} is not configured")
    return value


def _microsoft_oauth_settings() -> dict[str, str]:
    client_id = _required_env("MS_CLIENT_ID")
    client_secret = _required_env("MS_CLIENT_SECRET")
    redirect_uri = _required_env("MS_REDIRECT_URI")
    scopes = os.getenv("MS_GRAPH_SCOPES", "").strip() or DEFAULT_GRAPH_SCOPES
    post_connect_redirect = (
        os.getenv("MS_POST_CONNECT_REDIRECT", "").strip() or DEFAULT_POST_CONNECT_REDIRECT
    )
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "scopes": scopes,
        "post_connect_redirect": post_connect_redirect,
    }


def _post_connect_redirect_url(*, status_value: str, reason: str | None = None) -> str:
    base_url = (
        os.getenv("MS_POST_CONNECT_REDIRECT", "").strip() or DEFAULT_POST_CONNECT_REDIRECT
    )
    query = {"status": status_value}
    if reason:
        query["reason"] = _sanitize_reason(reason)
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode(query)}"


def _redirect_to_post_connect(*, status_value: str, reason: str | None = None) -> RedirectResponse:
    return RedirectResponse(
        _post_connect_redirect_url(status_value=status_value, reason=reason),
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _encode_state(*, organization_id: str, user_id: str, return_to: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "token_type": STATE_TOKEN_TYPE,
        "org_id": organization_id,
        "user_id": user_id,
        "nonce": secrets.token_urlsafe(16),
        "timestamp": int(now.timestamp()),
        "return_to": return_to,
        "exp": now + timedelta(minutes=STATE_TTL_MINUTES),
    }
    return jwt.encode(payload, _state_signing_secret(), algorithm=JWT_ALGORITHM)


def _decode_state(state: str) -> dict[str, str]:
    try:
        payload = jwt.decode(
            state,
            _state_signing_secret(),
            algorithms=[JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise ValueError("invalid_state") from exc

    if payload.get("token_type") != STATE_TOKEN_TYPE:
        raise ValueError("invalid_state_type")

    org_id = str(payload.get("org_id", "")).strip()
    user_id = str(payload.get("user_id", "")).strip()
    nonce = str(payload.get("nonce", "")).strip()
    if not org_id or not user_id or not nonce:
        raise ValueError("invalid_state_payload")

    return {
        "org_id": org_id,
        "user_id": user_id,
        "return_to": str(payload.get("return_to", "")).strip(),
    }


def _ensure_membership_for_state(*, db: Session, organization_id: str, user_id: str) -> OrganizationMembership:
    membership = db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
    ).scalar_one_or_none()
    if not membership:
        raise ValueError("state_membership_not_found")
    if not membership.user or not membership.user.is_active:
        raise ValueError("state_user_inactive")
    return membership


def _raise_graph_error(exc: MicrosoftGraphServiceError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail=exc.detail,
    ) from exc


def _id_token_identity(id_token: str) -> tuple[str, str, str | None]:
    try:
        claims = jwt.get_unverified_claims(id_token)
    except JWTError as exc:
        raise ValueError("invalid_id_token") from exc

    external_tenant_id = str(claims.get("tid", "")).strip()
    external_user_id = str(claims.get("oid", "")).strip()
    email_value = claims.get("preferred_username") or claims.get("email")
    email = str(email_value).strip() if email_value else None

    if not external_tenant_id or not external_user_id:
        raise ValueError("id_token_missing_subject_claims")
    return external_tenant_id, external_user_id, email


def _authorization_url_for_membership(membership: OrganizationMembership) -> str:
    settings = _microsoft_oauth_settings()
    state = _encode_state(
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        return_to=settings["post_connect_redirect"],
    )
    query = {
        "client_id": settings["client_id"],
        "response_type": "code",
        "redirect_uri": settings["redirect_uri"],
        "response_mode": "query",
        "scope": settings["scopes"],
        "state": state,
    }
    return f"{MICROSOFT_AUTHORIZE_URL}?{urlencode(query)}"


@router.get("/integrations/microsoft/connect")
def microsoft_connect(
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("org:manage")),
) -> MicrosoftConnectResponse:
    try:
        auth_url = _authorization_url_for_membership(membership)
    except MicrosoftOAuthConfigError as exc:
        logger.error("Microsoft OAuth connect configuration error: %s", str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Microsoft integration is not configured",
        ) from exc
    return MicrosoftConnectResponse(authorization_url=auth_url)


@router.post("/integrations/microsoft/test", response_model=MicrosoftConnectionTestResponse)
def microsoft_test_connection(
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("org:manage")),
) -> MicrosoftConnectionTestResponse:
    try:
        profile = get_microsoft_graph_profile(
            db=db,
            organization_id=membership.organization_id,
            user_id=membership.user_id,
        )
    except MicrosoftGraphServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc

    log_event(
        db,
        action="microsoft.test_connection",
        entity_type="integration",
        entity_id=membership.organization_id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={"provider": "microsoft"},
    )
    return MicrosoftConnectionTestResponse(
        display_name=profile.get("displayName"),
        user_principal_name=profile.get("userPrincipalName"),
    )


@router.post("/integrations/microsoft/refresh", response_model=MicrosoftRefreshResponse)
def microsoft_refresh_connection(
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("org:manage")),
) -> MicrosoftRefreshResponse:
    log_event(
        db,
        action="microsoft.refresh_connection_attempt",
        entity_type="integration",
        entity_id=membership.organization_id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={"provider": "microsoft"},
    )

    try:
        expires_at = refresh_microsoft_connection_tokens(
            db=db,
            organization_id=membership.organization_id,
            user_id=membership.user_id,
        )
    except MicrosoftGraphServiceError as exc:
        log_event(
            db,
            action="microsoft.refresh_connection_failed",
            entity_type="integration",
            entity_id=membership.organization_id,
            organization_id=membership.organization_id,
            actor=membership.user.email,
            metadata={"provider": "microsoft", "error": exc.detail},
        )
        _raise_graph_error(exc)

    log_event(
        db,
        action="microsoft.refresh_connection",
        entity_type="integration",
        entity_id=membership.organization_id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={"provider": "microsoft"},
    )
    return MicrosoftRefreshResponse(status="refreshed", expires_at=expires_at)


@router.post("/integrations/microsoft/disconnect", response_model=MicrosoftDisconnectResponse)
def microsoft_disconnect(
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("org:manage")),
) -> MicrosoftDisconnectResponse:
    now = datetime.now(timezone.utc)

    log_event(
        db,
        action="microsoft.disconnect_attempt",
        entity_type="integration",
        entity_id=membership.organization_id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={"provider": "microsoft"},
    )

    account = db.execute(
        select(IntegrationAccount).where(
            IntegrationAccount.organization_id == membership.organization_id,
            IntegrationAccount.user_id == membership.user_id,
            IntegrationAccount.provider == "microsoft",
            IntegrationAccount.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    if account is not None:
        account.revoked_at = now
        db.add(account)

    connection = db.execute(
        select(UserMicrosoftConnection).where(
            UserMicrosoftConnection.organization_id == membership.organization_id,
            UserMicrosoftConnection.user_id == membership.user_id,
            UserMicrosoftConnection.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    if connection is not None:
        connection.revoked_at = now
        connection.todo_list_id = None
        connection.access_token_enc = None
        connection.refresh_token_enc = None
        db.add(connection)

    db.commit()

    log_event(
        db,
        action="microsoft.disconnected",
        entity_type="integration",
        entity_id=membership.organization_id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={"provider": "microsoft"},
    )
    return MicrosoftDisconnectResponse(status="disconnected")


@router.get(
    "/integrations/microsoft/sharepoint/workspace",
    response_model=SharePointWorkspaceRead,
)
def microsoft_sharepoint_workspace(
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("org:manage")),
) -> SharePointWorkspaceRead:
    try:
        workspace = get_sharepoint_workspace(
            db=db,
            organization_id=membership.organization_id,
            user_id=membership.user_id,
        )
    except MicrosoftGraphServiceError as exc:
        _raise_graph_error(exc)

    log_event(
        db,
        action="microsoft.sharepoint.workspace_read",
        entity_type="sharepoint_site",
        entity_id=membership.organization_id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={"site_id": workspace.site.id},
    )

    return SharePointWorkspaceRead(
        site=SharePointSiteRead(
            id=workspace.site.id,
            name=workspace.site.name,
            web_url=workspace.site.web_url,
        ),
        drives=[
            SharePointDriveRead(
                id=drive.id,
                name=drive.name,
                web_url=drive.web_url,
            )
            for drive in workspace.drives
        ],
    )


@router.get(
    "/integrations/microsoft/sharepoint/drives/{drive_id}/items",
    response_model=list[SharePointItemRead],
)
def microsoft_sharepoint_drive_items(
    drive_id: str,
    parent_id: str = Query(default="root", alias="parentId"),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("org:manage")),
) -> list[SharePointItemRead]:
    try:
        items = list_sharepoint_drive_items(
            db=db,
            organization_id=membership.organization_id,
            user_id=membership.user_id,
            drive_id=drive_id,
            parent_id=parent_id,
        )
    except MicrosoftGraphServiceError as exc:
        _raise_graph_error(exc)

    log_event(
        db,
        action="microsoft.sharepoint.items_list",
        entity_type="sharepoint_drive",
        entity_id=membership.organization_id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={"drive_id": drive_id, "parent_id": parent_id},
    )

    return [
        SharePointItemRead(
            id=item.id,
            name=item.name,
            is_folder=item.is_folder,
            size=item.size,
            web_url=item.web_url,
            last_modified_date_time=item.last_modified,
            mime_type=item.mime_type,
        )
        for item in items
    ]


@router.get(
    "/integrations/microsoft/sharepoint/items/{item_id}/preview",
    response_model=SharePointItemPreviewRead,
)
def microsoft_sharepoint_item_preview(
    item_id: str,
    drive_id: str = Query(..., alias="driveId"),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("org:manage")),
) -> SharePointItemPreviewRead:
    try:
        preview = get_sharepoint_item_preview(
            db=db,
            organization_id=membership.organization_id,
            user_id=membership.user_id,
            item_id=item_id,
            drive_id=drive_id,
        )
    except MicrosoftGraphServiceError as exc:
        _raise_graph_error(exc)

    log_event(
        db,
        action="microsoft.sharepoint.preview",
        entity_type="sharepoint_item",
        entity_id=membership.organization_id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={
            "drive_id": drive_id,
            "item_id": item_id,
            "preview_kind": preview.preview_kind,
        },
    )

    return SharePointItemPreviewRead(
        id=preview.id,
        name=preview.name,
        web_url=preview.web_url,
        mime_type=preview.mime_type,
        preview_kind=preview.preview_kind,
        is_previewable=preview.is_previewable,
        preview_url=preview.preview_url,
        download_url=preview.download_url,
    )


@router.get("/integrations/microsoft/sharepoint/items/{item_id}/download")
def microsoft_sharepoint_item_download(
    item_id: str,
    drive_id: str = Query(..., alias="driveId"),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("org:manage")),
) -> StreamingResponse:
    try:
        payload = get_sharepoint_item_download_by_item(
            db=db,
            organization_id=membership.organization_id,
            user_id=membership.user_id,
            item_id=item_id,
            drive_id=drive_id,
        )
    except MicrosoftGraphServiceError as exc:
        _raise_graph_error(exc)

    log_event(
        db,
        action="microsoft.sharepoint.download",
        entity_type="sharepoint_item",
        entity_id=membership.organization_id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={"drive_id": drive_id, "item_id": item_id},
    )

    headers = {
        "Content-Disposition": f'inline; filename="{payload.filename}"',
        "Cache-Control": "no-store",
    }
    if payload.content_length is not None:
        headers["Content-Length"] = str(payload.content_length)
    if payload.web_url:
        headers["X-SharePoint-Web-Url"] = payload.web_url

    return StreamingResponse(
        payload.stream,
        media_type=payload.content_type or "application/octet-stream",
        headers=headers,
        status_code=status.HTTP_200_OK,
    )


@router.get("/integrations/microsoft/callback")
def microsoft_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if error:
        logger.warning(
            "Microsoft OAuth callback returned error code=%s description=%s",
            error,
            error_description or "",
        )
        return _redirect_to_post_connect(
            status_value="error",
            reason=f"microsoft_{error}",
        )

    if not code or not state:
        return _redirect_to_post_connect(status_value="error", reason="missing_code_or_state")

    try:
        decoded_state = _decode_state(state)
        settings = _microsoft_oauth_settings()
        membership = _ensure_membership_for_state(
            db=db,
            organization_id=decoded_state["org_id"],
            user_id=decoded_state["user_id"],
        )
        token_response = _exchange_code_for_tokens(code=code, settings=settings)

        refresh_token = str(token_response.get("refresh_token", "")).strip()
        if not refresh_token:
            raise ValueError("missing_refresh_token")

        id_token = str(token_response.get("id_token", "")).strip()
        if not id_token:
            raise ValueError("missing_id_token")

        external_tenant_id, external_user_id, email = _id_token_identity(id_token)
        scopes = str(token_response.get("scope", "")).strip() or settings["scopes"]

        refresh_token_enc = encrypt_token(refresh_token)
        access_token = str(token_response.get("access_token", "")).strip()
        access_token_enc = encrypt_token(access_token) if access_token else None
        account = _upsert_integration_account(
            db=db,
            organization_id=decoded_state["org_id"],
            user_id=decoded_state["user_id"],
            external_tenant_id=external_tenant_id,
            external_user_id=external_user_id,
            email=email,
            scopes=scopes,
            refresh_token_enc=refresh_token_enc,
        )

        log_event(
            db,
            action="microsoft.connected",
            entity_type="integration_account",
            entity_id=account.id,
            organization_id=decoded_state["org_id"],
            actor=membership.user.email,
            metadata={
                "provider": "microsoft",
                "user_id": decoded_state["user_id"],
                "external_tenant_id": external_tenant_id,
                "external_user_id": external_user_id,
            },
        )

        # Best-effort: persist an MSAL token cache for newer Graph client flows.
        try:
            scopes_list = _split_scopes(scopes)
            token_cache_encrypted = _build_token_cache_encrypted(
                token_response=token_response,
                client_id=settings["client_id"],
                tenant_id=external_tenant_id,
                msft_user_id=external_user_id,
                scopes=scopes_list,
                id_token=id_token,
            )
            _upsert_user_microsoft_connection(
                db=db,
                organization_id=decoded_state["org_id"],
                user_id=decoded_state["user_id"],
                tenant_id=external_tenant_id,
                msft_user_id=external_user_id,
                scopes=scopes_list,
                token_cache_encrypted=token_cache_encrypted,
                refresh_token_enc=refresh_token_enc,
                access_token_enc=access_token_enc,
                expires_at=_expires_at_from_response(token_response),
                connected_at=datetime.now(timezone.utc),
                revoked_at=None,
                metadata_json=_token_metadata(token_response),
            )
        except Exception:
            db.rollback()
            logger.exception("Microsoft OAuth token cache persistence failed")
    except MicrosoftOAuthConfigError as exc:
        logger.error("Microsoft OAuth callback configuration error: %s", str(exc))
        db.rollback()
        return _redirect_to_post_connect(status_value="error", reason="server_misconfigured")
    except TokenEncryptionError as exc:
        logger.error("Microsoft OAuth callback token encryption failed: %s", str(exc))
        db.rollback()
        return _redirect_to_post_connect(status_value="error", reason="token_encryption_failed")
    except ValueError as exc:
        logger.warning("Microsoft OAuth callback validation failed: %s", str(exc))
        db.rollback()
        return _redirect_to_post_connect(status_value="error", reason=str(exc))
    except Exception:
        logger.exception("Unexpected Microsoft OAuth callback failure")
        db.rollback()
        return _redirect_to_post_connect(status_value="error", reason="unexpected_error")

    return _redirect_to_post_connect(status_value="connected")


def _exchange_code_for_tokens(*, code: str, settings: dict[str, str]) -> dict[str, Any]:
    payload = {
        "client_id": settings["client_id"],
        "client_secret": settings["client_secret"],
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings["redirect_uri"],
        "scope": settings["scopes"],
    }

    try:
        response = httpx.post(
            MICROSOFT_TOKEN_URL,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise ValueError("token_exchange_failed") from exc

    body: dict[str, Any] = {}
    try:
        body = response.json()
    except Exception:
        body = {}

    if response.status_code >= 400:
        error_code = str(body.get("error", "")).strip() or f"http_{response.status_code}"
        raise ValueError(f"token_exchange_{_sanitize_reason(error_code)}")

    if not isinstance(body, dict):
        raise ValueError("invalid_token_response")
    return body


def _upsert_integration_account(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    external_tenant_id: str,
    external_user_id: str,
    email: str | None,
    scopes: str,
    refresh_token_enc: str,
) -> IntegrationAccount:
    row = db.execute(
        select(IntegrationAccount).where(
            IntegrationAccount.organization_id == organization_id,
            IntegrationAccount.provider == "microsoft",
            IntegrationAccount.external_tenant_id == external_tenant_id,
            IntegrationAccount.external_user_id == external_user_id,
        )
    ).scalar_one_or_none()

    if row:
        row.user_id = user_id
        row.email = email
        row.scopes = scopes
        row.refresh_token_enc = refresh_token_enc
        row.revoked_at = None
        db.add(row)
    else:
        row = IntegrationAccount(
            organization_id=organization_id,
            user_id=user_id,
            provider="microsoft",
            external_tenant_id=external_tenant_id,
            external_user_id=external_user_id,
            email=email,
            scopes=scopes,
            refresh_token_enc=refresh_token_enc,
            revoked_at=None,
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    return row


def _split_scopes(raw_scopes: str) -> list[str]:
    items = [item.strip() for item in (raw_scopes or "").split() if item.strip()]
    ordered: list[str] = []
    for item in items:
        if item not in ordered:
            ordered.append(item)
    return ordered


def _expires_at_from_response(token_response: dict[str, Any]) -> datetime | None:
    raw = token_response.get("expires_in")
    if raw is None:
        return datetime.now(timezone.utc) + timedelta(hours=1)
    try:
        seconds = int(raw)
    except Exception:
        return None
    if seconds <= 0:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def _token_metadata(token_response: dict[str, Any]) -> dict[str, Any]:
    return {
        "token_type": str(token_response.get("token_type", "")).strip() or None,
        "scope": str(token_response.get("scope", "")).strip() or None,
    }


def _encode_client_info(*, uid: str, utid: str) -> str:
    payload = json.dumps({"uid": uid, "utid": utid}, separators=(",", ":"), default=str).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("utf-8").rstrip("=")


def _build_token_cache_encrypted(
    *,
    token_response: dict[str, Any],
    client_id: str,
    tenant_id: str,
    msft_user_id: str,
    scopes: list[str],
    id_token: str,
) -> str:
    # Build an MSAL cache payload without re-redeeming the one-time auth code.
    cache = msal.SerializableTokenCache()
    claims = jwt.get_unverified_claims(id_token)

    augmented_response = dict(token_response)
    augmented_response["id_token_claims"] = claims
    augmented_response.setdefault("client_info", _encode_client_info(uid=msft_user_id, utid=tenant_id))

    cache.add(
        {
            "client_id": client_id,
            "scope": scopes,
            "token_endpoint": f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            "grant_type": "authorization_code",
            "response": augmented_response,
        }
    )
    return encrypt_token(cache.serialize())


def _upsert_user_microsoft_connection(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    tenant_id: str,
    msft_user_id: str | None,
    scopes: list[str],
    token_cache_encrypted: str,
    refresh_token_enc: str | None,
    access_token_enc: str | None,
    expires_at: datetime | None,
    connected_at: datetime | None,
    revoked_at: datetime | None,
    metadata_json: dict[str, Any] | None,
) -> UserMicrosoftConnection:
    row = db.execute(
        select(UserMicrosoftConnection).where(
            UserMicrosoftConnection.organization_id == organization_id,
            UserMicrosoftConnection.user_id == user_id,
        )
    ).scalar_one_or_none()

    if row:
        if msft_user_id and row.msft_user_id and row.msft_user_id != msft_user_id:
            row.todo_list_id = None
        row.tenant_id = tenant_id
        row.msft_user_id = msft_user_id
        row.scopes = scopes
        row.token_cache_encrypted = token_cache_encrypted
        if refresh_token_enc:
            row.refresh_token_enc = refresh_token_enc
        if access_token_enc:
            row.access_token_enc = access_token_enc
        if expires_at is not None:
            row.expires_at = expires_at
        if connected_at is not None:
            row.connected_at = connected_at
        row.revoked_at = revoked_at
        if metadata_json is not None:
            row.metadata_json = metadata_json
        db.add(row)
    else:
        row = UserMicrosoftConnection(
            organization_id=organization_id,
            user_id=user_id,
            tenant_id=tenant_id,
            msft_user_id=msft_user_id,
            scopes=scopes,
            token_cache_encrypted=token_cache_encrypted,
            refresh_token_enc=refresh_token_enc,
            access_token_enc=access_token_enc,
            expires_at=expires_at,
            connected_at=connected_at,
            revoked_at=revoked_at,
            metadata_json=metadata_json or {},
            todo_list_id=None,
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    return row
