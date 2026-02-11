from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import JWT_ALGORITHM, JWT_SECRET
from app.db.models.integration_token import IntegrationToken
from app.services.integration_tokens import TokenEncryptionError, decrypt_token, encrypt_token


RINGCENTRAL_PROVIDER = "ringcentral"
RINGCENTRAL_STATE_TOKEN_TYPE = "ringcentral_oauth_state"
RINGCENTRAL_STATE_TTL_MINUTES = 10

DEFAULT_RINGCENTRAL_SERVER_URL = "https://platform.ringcentral.com"
DEFAULT_RINGCENTRAL_SCOPES = "ReadAccounts ReadCallLog"
DEFAULT_POST_CONNECT_REDIRECT = "https://360-encompass.com/admin-center?ringcentral=connected"


class RingCentralIntegrationError(RuntimeError):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class RingCentralConfigurationError(RingCentralIntegrationError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail, status_code=500)


class RingCentralTokenMissingError(RingCentralIntegrationError):
    def __init__(self) -> None:
        super().__init__("RingCentral integration is not connected", status_code=404)


@dataclass(frozen=True)
class RingCentralOAuthSettings:
    client_id: str
    client_secret: str
    server_url: str
    redirect_uri: str
    scopes: str
    post_connect_redirect: str


@dataclass(frozen=True)
class RingCentralTokenPayload:
    access_token: str
    refresh_token: str
    expires_at: datetime | None
    scope: str | None
    account_id: str | None
    extension_id: str | None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _state_signing_secret() -> str:
    return os.getenv("STATE_SIGNING_KEY", "").strip() or JWT_SECRET


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RingCentralConfigurationError(f"{name} is not configured")
    return value


def load_ringcentral_oauth_settings() -> RingCentralOAuthSettings:
    return RingCentralOAuthSettings(
        client_id=_required_env("RINGCENTRAL_CLIENT_ID"),
        client_secret=_required_env("RINGCENTRAL_CLIENT_SECRET"),
        server_url=os.getenv("RINGCENTRAL_SERVER_URL", "").strip() or DEFAULT_RINGCENTRAL_SERVER_URL,
        redirect_uri=_required_env("RINGCENTRAL_REDIRECT_URI"),
        scopes=os.getenv("RINGCENTRAL_SCOPES", "").strip() or DEFAULT_RINGCENTRAL_SCOPES,
        post_connect_redirect=os.getenv("RINGCENTRAL_POST_CONNECT_REDIRECT", "").strip()
        or DEFAULT_POST_CONNECT_REDIRECT,
    )


def encode_ringcentral_state(*, organization_id: str, user_id: str) -> str:
    now = _now_utc()
    payload = {
        "token_type": RINGCENTRAL_STATE_TOKEN_TYPE,
        "org_id": organization_id,
        "user_id": user_id,
        "nonce": secrets.token_urlsafe(16),
        "exp": now + timedelta(minutes=RINGCENTRAL_STATE_TTL_MINUTES),
        "iat": int(now.timestamp()),
    }
    return jwt.encode(payload, _state_signing_secret(), algorithm=JWT_ALGORITHM)


def decode_ringcentral_state(state: str) -> dict[str, str]:
    try:
        payload = jwt.decode(
            state,
            _state_signing_secret(),
            algorithms=[JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise RingCentralIntegrationError("invalid_state", 400) from exc

    if payload.get("token_type") != RINGCENTRAL_STATE_TOKEN_TYPE:
        raise RingCentralIntegrationError("invalid_state_type", 400)

    org_id = str(payload.get("org_id", "")).strip()
    user_id = str(payload.get("user_id", "")).strip()
    nonce = str(payload.get("nonce", "")).strip()
    if not org_id or not user_id or not nonce:
        raise RingCentralIntegrationError("invalid_state_payload", 400)

    return {"org_id": org_id, "user_id": user_id}


def build_ringcentral_auth_url(*, settings: RingCentralOAuthSettings, state: str) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.client_id,
            "redirect_uri": settings.redirect_uri,
            "state": state,
        }
    )
    return f"{settings.server_url.rstrip('/')}/restapi/oauth/authorize?{query}"


def _oauth_token_url(settings: RingCentralOAuthSettings) -> str:
    return f"{settings.server_url.rstrip('/')}/restapi/oauth/token"


def _json_dict_or_empty(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except Exception:
        return {}
    if isinstance(body, dict):
        return body
    return {}


def exchange_code_for_tokens(
    *,
    settings: RingCentralOAuthSettings,
    code: str,
) -> RingCentralTokenPayload:
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.redirect_uri,
    }

    try:
        response = httpx.post(
            _oauth_token_url(settings),
            data=payload,
            auth=(settings.client_id, settings.client_secret),
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise RingCentralIntegrationError("token_exchange_failed", 502) from exc

    body = _json_dict_or_empty(response)
    if response.status_code >= 400:
        detail = str(body.get("error_description", "")).strip() or str(body.get("error", "")).strip() or "token_exchange_failed"
        raise RingCentralIntegrationError(detail, 502)

    access_token = str(body.get("access_token", "")).strip()
    refresh_token = str(body.get("refresh_token", "")).strip()
    if not access_token or not refresh_token:
        raise RingCentralIntegrationError("token_exchange_missing_tokens", 502)

    expires_in_raw = body.get("expires_in")
    expires_at: datetime | None = None
    try:
        if expires_in_raw is not None:
            expires_at = _now_utc() + timedelta(seconds=max(int(expires_in_raw), 0))
    except Exception:
        expires_at = None

    scope = str(body.get("scope", "")).strip() or settings.scopes
    return RingCentralTokenPayload(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        scope=scope,
        account_id=None,
        extension_id=None,
    )


def refresh_access_token(
    *,
    settings: RingCentralOAuthSettings,
    refresh_token: str,
) -> RingCentralTokenPayload:
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    try:
        response = httpx.post(
            _oauth_token_url(settings),
            data=payload,
            auth=(settings.client_id, settings.client_secret),
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise RingCentralIntegrationError("token_refresh_failed", 502) from exc

    body = _json_dict_or_empty(response)
    if response.status_code >= 400:
        detail = str(body.get("error_description", "")).strip() or str(body.get("error", "")).strip() or "token_refresh_failed"
        raise RingCentralIntegrationError(detail, 502)

    access_token = str(body.get("access_token", "")).strip()
    next_refresh_token = str(body.get("refresh_token", "")).strip() or refresh_token
    if not access_token or not next_refresh_token:
        raise RingCentralIntegrationError("token_refresh_missing_tokens", 502)

    expires_in_raw = body.get("expires_in")
    expires_at: datetime | None = None
    try:
        if expires_in_raw is not None:
            expires_at = _now_utc() + timedelta(seconds=max(int(expires_in_raw), 0))
    except Exception:
        expires_at = None

    scope = str(body.get("scope", "")).strip() or settings.scopes
    return RingCentralTokenPayload(
        access_token=access_token,
        refresh_token=next_refresh_token,
        expires_at=expires_at,
        scope=scope,
        account_id=None,
        extension_id=None,
    )


def fetch_account_identifiers(
    *,
    settings: RingCentralOAuthSettings,
    access_token: str,
) -> tuple[str | None, str | None]:
    headers = {"Authorization": f"Bearer {access_token}"}
    account_id: str | None = None
    extension_id: str | None = None

    try:
        extension_response = httpx.get(
            f"{settings.server_url.rstrip('/')}/restapi/v1.0/account/~/extension/~",
            headers=headers,
            timeout=20.0,
        )
        if extension_response.status_code < 400:
            body = _json_dict_or_empty(extension_response)
            extension_id = str(body.get("id", "")).strip() or None
            account_id = str(body.get("accountId", "")).strip() or None
    except httpx.HTTPError:
        pass

    if account_id:
        return account_id, extension_id

    try:
        account_response = httpx.get(
            f"{settings.server_url.rstrip('/')}/restapi/v1.0/account/~",
            headers=headers,
            timeout=20.0,
        )
        if account_response.status_code < 400:
            body = _json_dict_or_empty(account_response)
            account_id = str(body.get("id", "")).strip() or None
    except httpx.HTTPError:
        pass

    return account_id, extension_id


def upsert_ringcentral_token(
    *,
    db: Session,
    organization_id: str,
    token_payload: RingCentralTokenPayload,
) -> IntegrationToken:
    try:
        access_token_enc = encrypt_token(token_payload.access_token)
        refresh_token_enc = encrypt_token(token_payload.refresh_token)
    except TokenEncryptionError as exc:
        raise RingCentralIntegrationError(str(exc), 500) from exc

    row = db.execute(
        select(IntegrationToken).where(
            IntegrationToken.organization_id == organization_id,
            IntegrationToken.provider == RINGCENTRAL_PROVIDER,
        )
    ).scalar_one_or_none()

    if row:
        row.access_token_enc = access_token_enc
        row.refresh_token_enc = refresh_token_enc
        row.expires_at = token_payload.expires_at
        row.scope = token_payload.scope
        row.account_id = token_payload.account_id
        row.extension_id = token_payload.extension_id
        db.add(row)
    else:
        row = IntegrationToken(
            organization_id=organization_id,
            provider=RINGCENTRAL_PROVIDER,
            access_token_enc=access_token_enc,
            refresh_token_enc=refresh_token_enc,
            expires_at=token_payload.expires_at,
            scope=token_payload.scope,
            account_id=token_payload.account_id,
            extension_id=token_payload.extension_id,
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    return row


def get_ringcentral_token_row(*, db: Session, organization_id: str) -> IntegrationToken | None:
    return db.execute(
        select(IntegrationToken).where(
            IntegrationToken.organization_id == organization_id,
            IntegrationToken.provider == RINGCENTRAL_PROVIDER,
        )
    ).scalar_one_or_none()


def disconnect_ringcentral(*, db: Session, organization_id: str) -> bool:
    row = get_ringcentral_token_row(db=db, organization_id=organization_id)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def resolve_access_token_for_org(
    *,
    db: Session,
    organization_id: str,
    min_validity_seconds: int = 30,
) -> tuple[str, IntegrationToken]:
    row = get_ringcentral_token_row(db=db, organization_id=organization_id)
    if not row:
        raise RingCentralTokenMissingError()

    now = _now_utc()
    expires_at = row.expires_at
    should_refresh = True
    if expires_at is not None:
        expiry = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
        should_refresh = expiry <= (now + timedelta(seconds=min_validity_seconds))

    if not should_refresh:
        try:
            return decrypt_token(row.access_token_enc), row
        except TokenEncryptionError as exc:
            raise RingCentralIntegrationError(str(exc), 500) from exc

    try:
        decrypted_refresh_token = decrypt_token(row.refresh_token_enc)
    except TokenEncryptionError as exc:
        raise RingCentralIntegrationError(str(exc), 500) from exc

    settings = load_ringcentral_oauth_settings()
    refreshed = refresh_access_token(settings=settings, refresh_token=decrypted_refresh_token)
    enriched = RingCentralTokenPayload(
        access_token=refreshed.access_token,
        refresh_token=refreshed.refresh_token,
        expires_at=refreshed.expires_at,
        scope=refreshed.scope,
        account_id=row.account_id,
        extension_id=row.extension_id,
    )
    next_row = upsert_ringcentral_token(
        db=db,
        organization_id=organization_id,
        token_payload=enriched,
    )
    return refreshed.access_token, next_row
