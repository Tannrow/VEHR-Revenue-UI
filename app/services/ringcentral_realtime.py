from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any
from urllib.parse import urlencode

import httpx
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import JWT_ALGORITHM
from app.db.models.ringcentral_credential import RingCentralCredential
from app.db.models.ringcentral_subscription import RingCentralSubscription
from app.services.integration_tokens import TokenEncryptionError, decrypt_token, encrypt_token


RINGCENTRAL_STATE_TOKEN_TYPE = "ringcentral_oauth_state"
RINGCENTRAL_STATE_TTL_SECONDS = 10 * 60
DEFAULT_RINGCENTRAL_SCOPES = "ReadAccounts ReadCallLog ReadPresence"
DEFAULT_STATE_RETURN_TO = "https://360-encompass.com/admin-center"
DEFAULT_EVENT_FILTERS = [
    "/restapi/v1.0/account/~/extension/~/telephony/sessions",
    "/restapi/v1.0/account/~/extension/~/presence?detailedTelephonyState=true",
]
SUBSCRIPTION_RENEWAL_WINDOW_SECONDS = 5 * 60
SUBSCRIPTION_EXPIRES_IN_SECONDS = 60 * 60 * 24 * 7
TOKEN_REFRESH_WINDOW_SECONDS = 90


class RingCentralRealtimeError(RuntimeError):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class RingCentralRuntimeConfig:
    client_id: str
    client_secret: str
    server_url: str
    redirect_uri: str
    webhook_shared_secret: str | None
    public_webhook_base_url: str | None
    scopes: str
    default_return_to: str
    integration_token_key: str


@dataclass(frozen=True)
class RingCentralOAuthTokenPayload:
    access_token: str
    refresh_token: str
    expires_at: datetime
    scopes: str | None
    account_id: str | None
    extension_id: str | None


@dataclass(frozen=True)
class ParsedRingCentralState:
    organization_id: str
    user_id: str
    nonce: str
    return_to: str
    issued_at: datetime


@dataclass(frozen=True)
class NormalizedCallEvent:
    rc_call_id: str
    session_id: str | None
    from_number: str | None
    to_number: str | None
    direction: str | None
    state: str
    disposition: str | None
    started_at: datetime | None
    ended_at: datetime | None
    account_id: str | None
    extension_id: str | None
    rc_event_id: str | None
    event_filter: str
    event_time: datetime
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class NormalizedPresenceEvent:
    extension_id: str | None
    account_id: str | None
    status: str
    dnd_status: str | None
    rc_event_id: str | None
    event_filter: str
    event_time: datetime
    raw_payload: dict[str, Any]


_refresh_locks_guard = Lock()
_refresh_locks: dict[tuple[str, str], Lock] = {}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RingCentralRealtimeError(f"{name} is not configured", status_code=500)
    return value


def _webhook_shared_secret_from_env() -> str:
    return (
        os.getenv("RINGCENTRAL_WEBHOOK_SHARED_SECRET", "").strip()
        or os.getenv("RINGCENTRAL_WEBHOOK_SECRET", "").strip()
    )


def load_ringcentral_runtime_config() -> RingCentralRuntimeConfig:
    integration_key = _required_env("INTEGRATION_TOKEN_KEY")
    return RingCentralRuntimeConfig(
        client_id=_required_env("RINGCENTRAL_CLIENT_ID"),
        client_secret=_required_env("RINGCENTRAL_CLIENT_SECRET"),
        server_url=_required_env("RINGCENTRAL_SERVER_URL"),
        redirect_uri=_required_env("RINGCENTRAL_REDIRECT_URI"),
        webhook_shared_secret=_webhook_shared_secret_from_env() or None,
        public_webhook_base_url=os.getenv("PUBLIC_WEBHOOK_BASE_URL", "").strip() or None,
        scopes=os.getenv("RINGCENTRAL_SCOPES", "").strip() or DEFAULT_RINGCENTRAL_SCOPES,
        default_return_to=os.getenv("RINGCENTRAL_POST_CONNECT_REDIRECT", "").strip() or DEFAULT_STATE_RETURN_TO,
        integration_token_key=integration_key,
    )


def validate_ringcentral_startup_configuration() -> None:
    config = load_ringcentral_runtime_config()
    probe_plaintext = "ringcentral-startup-probe"
    try:
        probe_encrypted = encrypt_token(probe_plaintext, key_env="INTEGRATION_TOKEN_KEY")
        probe_roundtrip = decrypt_token(probe_encrypted, key_env="INTEGRATION_TOKEN_KEY")
    except TokenEncryptionError as exc:
        raise RingCentralRealtimeError(f"INTEGRATION_TOKEN_KEY validation failed: {exc}", status_code=500) from exc
    if probe_roundtrip != probe_plaintext:
        raise RingCentralRealtimeError("INTEGRATION_TOKEN_KEY validation failed", status_code=500)
    if not config.redirect_uri:
        raise RingCentralRealtimeError("RINGCENTRAL_REDIRECT_URI is not configured", status_code=500)


def _state_signing_secret(config: RingCentralRuntimeConfig) -> str:
    digest = hashlib.sha256(config.integration_token_key.encode("utf-8")).hexdigest()
    return f"ringcentral-state::{digest}"


def make_state(
    *,
    config: RingCentralRuntimeConfig,
    organization_id: str,
    user_id: str,
    return_to: str,
) -> str:
    now = _now_utc()
    payload = {
        "token_type": RINGCENTRAL_STATE_TOKEN_TYPE,
        "org_id": organization_id,
        "user_id": user_id,
        "nonce": secrets.token_urlsafe(16),
        "return_to": return_to,
        "issued_at": int(now.timestamp()),
        "exp": now + timedelta(seconds=RINGCENTRAL_STATE_TTL_SECONDS),
    }
    return jwt.encode(payload, _state_signing_secret(config), algorithm=JWT_ALGORITHM)


def parse_state(*, config: RingCentralRuntimeConfig, state: str) -> ParsedRingCentralState:
    try:
        payload = jwt.decode(state, _state_signing_secret(config), algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise RingCentralRealtimeError("invalid_state_signature", 400) from exc

    if payload.get("token_type") != RINGCENTRAL_STATE_TOKEN_TYPE:
        raise RingCentralRealtimeError("invalid_state_type", 400)

    organization_id = str(payload.get("org_id", "")).strip()
    user_id = str(payload.get("user_id", "")).strip()
    nonce = str(payload.get("nonce", "")).strip()
    return_to = str(payload.get("return_to", "")).strip() or config.default_return_to
    issued_at_raw = payload.get("issued_at")

    if not organization_id or not user_id or not nonce:
        raise RingCentralRealtimeError("invalid_state_payload", 400)

    try:
        issued_at = datetime.fromtimestamp(int(issued_at_raw), tz=timezone.utc)
    except Exception as exc:
        raise RingCentralRealtimeError("invalid_state_issued_at", 400) from exc

    if _now_utc() - issued_at > timedelta(seconds=RINGCENTRAL_STATE_TTL_SECONDS):
        raise RingCentralRealtimeError("state_expired", 400)

    return ParsedRingCentralState(
        organization_id=organization_id,
        user_id=user_id,
        nonce=nonce,
        return_to=return_to,
        issued_at=issued_at,
    )


def build_authorization_url(*, config: RingCentralRuntimeConfig, state: str) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "state": state,
        }
    )
    return f"{config.server_url.rstrip('/')}/restapi/oauth/authorize?{query}"


def _token_endpoint(config: RingCentralRuntimeConfig) -> str:
    return f"{config.server_url.rstrip('/')}/restapi/oauth/token"


def _as_dict(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _parse_expiration(raw_value: Any) -> datetime | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, str) and raw_value.strip():
        normalized = raw_value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None
    try:
        seconds = int(raw_value)
    except Exception:
        return None
    return _now_utc() + timedelta(seconds=max(seconds, 0))


def _parse_token_expiration(raw_value: Any) -> datetime:
    parsed = _parse_expiration(raw_value)
    if parsed:
        return parsed
    return _now_utc() + timedelta(hours=1)


def exchange_authorization_code(
    *,
    config: RingCentralRuntimeConfig,
    code: str,
) -> RingCentralOAuthTokenPayload:
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.redirect_uri,
    }
    try:
        response = httpx.post(
            _token_endpoint(config),
            data=payload,
            auth=(config.client_id, config.client_secret),
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise RingCentralRealtimeError("token_exchange_failed", 502) from exc

    body = _as_dict(response)
    if response.status_code >= 400:
        detail = str(body.get("error_description", "")).strip() or str(body.get("error", "")).strip() or "token_exchange_failed"
        raise RingCentralRealtimeError(detail, 502)

    access_token = str(body.get("access_token", "")).strip()
    refresh_token = str(body.get("refresh_token", "")).strip()
    if not access_token or not refresh_token:
        raise RingCentralRealtimeError("token_exchange_missing_tokens", 502)

    expires_at = _parse_token_expiration(body.get("expires_in"))
    scopes = str(body.get("scope", "")).strip() or config.scopes
    return RingCentralOAuthTokenPayload(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        scopes=scopes,
        account_id=None,
        extension_id=None,
    )


def refresh_access_token(
    *,
    config: RingCentralRuntimeConfig,
    refresh_token: str,
) -> RingCentralOAuthTokenPayload:
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    try:
        response = httpx.post(
            _token_endpoint(config),
            data=payload,
            auth=(config.client_id, config.client_secret),
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise RingCentralRealtimeError("token_refresh_failed", 502) from exc

    body = _as_dict(response)
    if response.status_code >= 400:
        detail = str(body.get("error_description", "")).strip() or str(body.get("error", "")).strip() or "token_refresh_failed"
        raise RingCentralRealtimeError(detail, 502)

    access_token = str(body.get("access_token", "")).strip()
    next_refresh_token = str(body.get("refresh_token", "")).strip() or refresh_token
    if not access_token:
        raise RingCentralRealtimeError("token_refresh_missing_access_token", 502)

    expires_at = _parse_token_expiration(body.get("expires_in"))
    scopes = str(body.get("scope", "")).strip() or config.scopes
    return RingCentralOAuthTokenPayload(
        access_token=access_token,
        refresh_token=next_refresh_token,
        expires_at=expires_at,
        scopes=scopes,
        account_id=None,
        extension_id=None,
    )


def fetch_account_and_extension(
    *,
    config: RingCentralRuntimeConfig,
    access_token: str,
) -> tuple[str | None, str | None]:
    headers = {"Authorization": f"Bearer {access_token}"}
    account_id: str | None = None
    extension_id: str | None = None

    try:
        response = httpx.get(
            f"{config.server_url.rstrip('/')}/restapi/v1.0/account/~/extension/~",
            headers=headers,
            timeout=20.0,
        )
        body = _as_dict(response)
        if response.status_code < 400:
            extension_id = str(body.get("id", "")).strip() or None
            account_id = str(body.get("accountId", "")).strip() or None
    except httpx.HTTPError:
        pass

    if account_id:
        return account_id, extension_id

    try:
        response = httpx.get(
            f"{config.server_url.rstrip('/')}/restapi/v1.0/account/~",
            headers=headers,
            timeout=20.0,
        )
        body = _as_dict(response)
        if response.status_code < 400:
            account_id = str(body.get("id", "")).strip() or None
    except httpx.HTTPError:
        pass

    return account_id, extension_id


def get_credential(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
) -> RingCentralCredential | None:
    return db.execute(
        select(RingCentralCredential).where(
            RingCentralCredential.organization_id == organization_id,
            RingCentralCredential.user_id == user_id,
        )
    ).scalar_one_or_none()


def upsert_credential(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    token: RingCentralOAuthTokenPayload,
) -> RingCentralCredential:
    try:
        access_token_enc = encrypt_token(token.access_token, key_env="INTEGRATION_TOKEN_KEY")
        refresh_token_enc = encrypt_token(token.refresh_token, key_env="INTEGRATION_TOKEN_KEY")
    except TokenEncryptionError as exc:
        raise RingCentralRealtimeError(str(exc), 500) from exc

    row = get_credential(db=db, organization_id=organization_id, user_id=user_id)
    if row:
        row.access_token_enc = access_token_enc
        row.refresh_token_enc = refresh_token_enc
        row.token_expires_at = token.expires_at
        row.scopes = token.scopes
        row.rc_account_id = token.account_id
        row.rc_extension_id = token.extension_id
        db.add(row)
    else:
        row = RingCentralCredential(
            organization_id=organization_id,
            user_id=user_id,
            rc_account_id=token.account_id,
            rc_extension_id=token.extension_id,
            access_token_enc=access_token_enc,
            refresh_token_enc=refresh_token_enc,
            token_expires_at=token.expires_at,
            scopes=token.scopes,
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    return row


def readback_credential(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
) -> RingCentralCredential:
    row = get_credential(db=db, organization_id=organization_id, user_id=user_id)
    if not row:
        raise RingCentralRealtimeError("credential_readback_failed", 500)
    return row


def disconnect_credential(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
) -> bool:
    row = get_credential(db=db, organization_id=organization_id, user_id=user_id)
    if not row:
        return False
    db.delete(row)
    sub = get_subscription(db=db, organization_id=organization_id, user_id=user_id)
    if sub:
        db.delete(sub)
    db.commit()
    return True


@contextmanager
def refresh_lock_for(organization_id: str, user_id: str):
    key = (organization_id, user_id)
    with _refresh_locks_guard:
        lock = _refresh_locks.setdefault(key, Lock())
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def get_valid_access_token(
    *,
    db: Session,
    config: RingCentralRuntimeConfig,
    organization_id: str,
    user_id: str,
) -> tuple[str, RingCentralCredential]:
    row = get_credential(db=db, organization_id=organization_id, user_id=user_id)
    if not row:
        raise RingCentralRealtimeError("ringcentral_not_connected", 404)

    now = _now_utc()
    expires_at = row.token_expires_at
    if expires_at is not None:
        expiry = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
        if expiry > now + timedelta(seconds=TOKEN_REFRESH_WINDOW_SECONDS):
            try:
                token = decrypt_token(row.access_token_enc, key_env="INTEGRATION_TOKEN_KEY")
                return token, row
            except TokenEncryptionError as exc:
                raise RingCentralRealtimeError(str(exc), 500) from exc

    with refresh_lock_for(organization_id, user_id):
        row = get_credential(db=db, organization_id=organization_id, user_id=user_id)
        if not row:
            raise RingCentralRealtimeError("ringcentral_not_connected", 404)

        expires_at = row.token_expires_at
        if expires_at is not None:
            expiry = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
            if expiry > _now_utc() + timedelta(seconds=TOKEN_REFRESH_WINDOW_SECONDS):
                try:
                    token = decrypt_token(row.access_token_enc, key_env="INTEGRATION_TOKEN_KEY")
                    return token, row
                except TokenEncryptionError as exc:
                    raise RingCentralRealtimeError(str(exc), 500) from exc

        try:
            refresh_token_plain = decrypt_token(row.refresh_token_enc, key_env="INTEGRATION_TOKEN_KEY")
        except TokenEncryptionError as exc:
            raise RingCentralRealtimeError(str(exc), 500) from exc

        refreshed = refresh_access_token(config=config, refresh_token=refresh_token_plain)
        refreshed_with_identity = RingCentralOAuthTokenPayload(
            access_token=refreshed.access_token,
            refresh_token=refreshed.refresh_token,
            expires_at=refreshed.expires_at,
            scopes=refreshed.scopes or row.scopes,
            account_id=row.rc_account_id,
            extension_id=row.rc_extension_id,
        )
        updated = upsert_credential(
            db=db,
            organization_id=organization_id,
            user_id=user_id,
            token=refreshed_with_identity,
        )
        return refreshed.access_token, updated


def get_subscription(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
) -> RingCentralSubscription | None:
    return db.execute(
        select(RingCentralSubscription).where(
            RingCentralSubscription.organization_id == organization_id,
            RingCentralSubscription.user_id == user_id,
        )
    ).scalar_one_or_none()


def _subscription_url(config: RingCentralRuntimeConfig) -> str:
    return f"{config.server_url.rstrip('/')}/restapi/v1.0/subscription"


def _subscription_item_url(config: RingCentralRuntimeConfig, rc_subscription_id: str) -> str:
    return f"{_subscription_url(config)}/{rc_subscription_id}"


def build_webhook_address(config: RingCentralRuntimeConfig) -> str:
    if not config.webhook_shared_secret:
        raise RingCentralRealtimeError("RINGCENTRAL_WEBHOOK_SHARED_SECRET is not configured", status_code=500)
    if not config.public_webhook_base_url:
        raise RingCentralRealtimeError("PUBLIC_WEBHOOK_BASE_URL is not configured", status_code=500)
    query = urlencode({"secret": config.webhook_shared_secret})
    return f"{config.public_webhook_base_url.rstrip('/')}/api/v1/webhooks/ringcentral?{query}"


def _subscription_payload(
    *,
    config: RingCentralRuntimeConfig,
    event_filters: list[str],
    expires_in: int = SUBSCRIPTION_EXPIRES_IN_SECONDS,
) -> dict[str, object]:
    if not config.webhook_shared_secret:
        raise RingCentralRealtimeError("RINGCENTRAL_WEBHOOK_SHARED_SECRET is not configured", status_code=500)
    return {
        "eventFilters": event_filters,
        "deliveryMode": {
            "transportType": "WebHook",
            "address": build_webhook_address(config),
            "verificationToken": config.webhook_shared_secret,
        },
        "expiresIn": expires_in,
    }


def _parse_subscription_expiry(body: dict[str, Any]) -> datetime | None:
    return _parse_expiration(body.get("expirationTime")) or _parse_expiration(body.get("expiresIn"))


def create_subscription(
    *,
    config: RingCentralRuntimeConfig,
    access_token: str,
    event_filters: list[str],
) -> tuple[str, datetime | None]:
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = _subscription_payload(config=config, event_filters=event_filters)
    try:
        response = httpx.post(
            _subscription_url(config),
            json=payload,
            headers=headers,
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise RingCentralRealtimeError("subscription_create_failed", 502) from exc

    body = _as_dict(response)
    if response.status_code >= 400:
        detail = str(body.get("message", "")).strip() or "subscription_create_failed"
        raise RingCentralRealtimeError(detail, 502)

    rc_subscription_id = str(body.get("id", "")).strip()
    if not rc_subscription_id:
        raise RingCentralRealtimeError("subscription_create_missing_id", 502)
    return rc_subscription_id, _parse_subscription_expiry(body)


def renew_subscription(
    *,
    config: RingCentralRuntimeConfig,
    access_token: str,
    rc_subscription_id: str,
    event_filters: list[str],
) -> tuple[str, datetime | None]:
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = _subscription_payload(config=config, event_filters=event_filters)
    try:
        response = httpx.put(
            _subscription_item_url(config, rc_subscription_id),
            json=payload,
            headers=headers,
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise RingCentralRealtimeError("subscription_renew_failed", 502) from exc

    body = _as_dict(response)
    if response.status_code >= 400:
        detail = str(body.get("message", "")).strip() or "subscription_renew_failed"
        raise RingCentralRealtimeError(detail, 502)

    next_id = str(body.get("id", "")).strip() or rc_subscription_id
    return next_id, _parse_subscription_expiry(body)


def upsert_subscription(
    *,
    db: Session,
    organization_id: str,
    user_id: str,
    rc_subscription_id: str | None,
    event_filters: list[str],
    expires_at: datetime | None,
    status: str,
) -> RingCentralSubscription:
    row = get_subscription(db=db, organization_id=organization_id, user_id=user_id)
    if row:
        row.rc_subscription_id = rc_subscription_id
        row.event_filters_json = json.dumps(event_filters)
        row.expires_at = expires_at
        row.status = status
        db.add(row)
    else:
        row = RingCentralSubscription(
            organization_id=organization_id,
            user_id=user_id,
            rc_subscription_id=rc_subscription_id,
            event_filters_json=json.dumps(event_filters),
            expires_at=expires_at,
            status=status,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def ensure_subscription(
    *,
    db: Session,
    config: RingCentralRuntimeConfig,
    organization_id: str,
    user_id: str,
    force: bool = False,
) -> RingCentralSubscription:
    access_token, _credential = get_valid_access_token(
        db=db,
        config=config,
        organization_id=organization_id,
        user_id=user_id,
    )
    event_filters = DEFAULT_EVENT_FILTERS
    current = get_subscription(db=db, organization_id=organization_id, user_id=user_id)
    now = _now_utc()
    should_create = force or not current or not current.rc_subscription_id
    should_renew = False

    if current and current.expires_at is not None:
        expiry = current.expires_at if current.expires_at.tzinfo else current.expires_at.replace(tzinfo=timezone.utc)
        should_renew = force or (expiry <= now + timedelta(seconds=SUBSCRIPTION_RENEWAL_WINDOW_SECONDS))
    elif current and current.rc_subscription_id:
        should_renew = True

    try:
        if should_create:
            rc_subscription_id, expires_at = create_subscription(
                config=config,
                access_token=access_token,
                event_filters=event_filters,
            )
        elif should_renew and current and current.rc_subscription_id:
            rc_subscription_id, expires_at = renew_subscription(
                config=config,
                access_token=access_token,
                rc_subscription_id=current.rc_subscription_id,
                event_filters=event_filters,
            )
        else:
            return current
    except RingCentralRealtimeError:
        upsert_subscription(
            db=db,
            organization_id=organization_id,
            user_id=user_id,
            rc_subscription_id=current.rc_subscription_id if current else None,
            event_filters=event_filters,
            expires_at=current.expires_at if current else None,
            status="ERROR",
        )
        raise

    return upsert_subscription(
        db=db,
        organization_id=organization_id,
        user_id=user_id,
        rc_subscription_id=rc_subscription_id,
        event_filters=event_filters,
        expires_at=expires_at,
        status="ACTIVE",
    )


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_extension_id(event_filter: str, body: dict[str, Any]) -> str | None:
    extension_id = str(body.get("extensionId", "")).strip()
    if extension_id:
        return extension_id
    extension_obj = body.get("extension")
    if isinstance(extension_obj, dict):
        candidate = str(extension_obj.get("id", "")).strip()
        if candidate:
            return candidate
    matched = re.search(r"/extension/([^/\?]+)", event_filter or "")
    if matched:
        candidate = matched.group(1).strip()
        if candidate and candidate != "~":
            return candidate
    return None


def _normalize_call_state(code: str | None, reason: str | None) -> tuple[str, str | None]:
    raw_code = (code or "").strip().lower()
    raw_reason = (reason or "").strip().lower()
    missed = {"missed", "noanswer", "no_answer", "busy", "declined", "rejected", "voicemail"}
    answered = {"answered", "connected"}
    ringing = {"ringing", "proceeding"}

    if raw_reason in missed:
        return "missed", "missed"
    if raw_reason in answered:
        return "answered", "answered"
    if raw_reason in ringing:
        return "ringing", "ringing"

    if raw_code in answered:
        return "answered", raw_code
    if raw_code in ringing:
        return "ringing", raw_code
    if raw_code in {"disconnected", "ended"}:
        if raw_reason in missed:
            return "missed", "missed"
        return "ended", raw_code
    if raw_code in missed:
        return "missed", "missed"
    if raw_code:
        return raw_code, raw_code
    return "unknown", None


def extract_account_id_from_payload(payload: dict[str, Any]) -> str | None:
    body_value = payload.get("body")
    body = body_value if isinstance(body_value, dict) else payload

    parties_raw = body.get("parties")
    if isinstance(parties_raw, list):
        for item in parties_raw:
            if not isinstance(item, dict):
                continue
            account_id = str(item.get("accountId", "")).strip()
            if account_id:
                return account_id

    account_id = str(body.get("accountId", "")).strip()
    if account_id:
        return account_id
    account_id = str(payload.get("accountId", "")).strip()
    if account_id:
        return account_id

    event_filter = str(payload.get("event", "")).strip()
    match = re.search(r"/account/([^/\?]+)", event_filter)
    if match:
        candidate = match.group(1).strip()
        if candidate and candidate != "~":
            return candidate
    return None


def normalize_webhook_events(payload: dict[str, Any]) -> tuple[list[NormalizedCallEvent], list[NormalizedPresenceEvent]]:
    event_filter = str(payload.get("event", "")).strip()
    rc_event_id = str(payload.get("uuid", "")).strip() or str(payload.get("eventId", "")).strip() or None
    body_value = payload.get("body")
    body = body_value if isinstance(body_value, dict) else payload
    event_time = _now_utc()

    call_events: list[NormalizedCallEvent] = []
    presence_events: list[NormalizedPresenceEvent] = []

    account_id = extract_account_id_from_payload(payload)

    if "telephony/sessions" in event_filter:
        session_id = str(body.get("telephonySessionId", "")).strip() or str(body.get("sessionId", "")).strip() or None
        rc_call_id = str(body.get("id", "")).strip() or session_id or rc_event_id
        if rc_call_id:
            parties_raw = body.get("parties")
            party: dict[str, Any] = {}
            if isinstance(parties_raw, list) and parties_raw and isinstance(parties_raw[0], dict):
                party = parties_raw[0]
            elif isinstance(body.get("party"), dict):
                party = body["party"]

            from_number = None
            to_number = None
            if isinstance(party.get("from"), dict):
                from_number = str(party["from"].get("phoneNumber", "")).strip() or None
            elif isinstance(body.get("from"), dict):
                from_number = str(body["from"].get("phoneNumber", "")).strip() or None
            if isinstance(party.get("to"), dict):
                to_number = str(party["to"].get("phoneNumber", "")).strip() or None
            elif isinstance(body.get("to"), dict):
                to_number = str(body["to"].get("phoneNumber", "")).strip() or None

            status_obj = party.get("status") if isinstance(party, dict) else None
            code = None
            reason = None
            if isinstance(status_obj, dict):
                code = str(status_obj.get("code", "")).strip() or None
                reason = str(status_obj.get("reason", "")).strip() or None
            elif isinstance(body.get("status"), dict):
                code = str(body["status"].get("code", "")).strip() or None
                reason = str(body["status"].get("reason", "")).strip() or None
            elif isinstance(body.get("status"), str):
                code = str(body.get("status", "")).strip() or None

            state, disposition = _normalize_call_state(code, reason)
            extension_id = _extract_extension_id(event_filter, body)
            direction = str(party.get("direction", "")).strip() or str(body.get("direction", "")).strip() or None
            started_at = _parse_iso_datetime(party.get("startTime")) or _parse_iso_datetime(body.get("startTime"))
            ended_at = _parse_iso_datetime(party.get("endTime")) or _parse_iso_datetime(body.get("endTime"))

            call_events.append(
                NormalizedCallEvent(
                    rc_call_id=rc_call_id,
                    session_id=session_id,
                    from_number=from_number,
                    to_number=to_number,
                    direction=direction,
                    state=state,
                    disposition=disposition,
                    started_at=started_at,
                    ended_at=ended_at,
                    account_id=account_id,
                    extension_id=extension_id,
                    rc_event_id=rc_event_id,
                    event_filter=event_filter,
                    event_time=event_time,
                    raw_payload=payload,
                )
            )

    if "presence" in event_filter:
        extension_id = _extract_extension_id(event_filter, body)
        presence_status = str(body.get("presenceStatus", "")).strip() or str(body.get("telephonyStatus", "")).strip()
        dnd_status = str(body.get("dndStatus", "")).strip() or None
        normalized = presence_status.lower() or "unknown"
        if normalized in {"available", "no_call", "idle"}:
            normalized = "available"
        elif normalized in {"onhold", "ringing", "callconnected", "busy"}:
            normalized = "on_call"
        elif normalized in {"offline", "invisible"}:
            normalized = "offline"

        presence_events.append(
            NormalizedPresenceEvent(
                extension_id=extension_id,
                account_id=account_id,
                status=normalized,
                dnd_status=dnd_status,
                rc_event_id=rc_event_id,
                event_filter=event_filter,
                event_time=event_time,
                raw_payload=payload,
            )
        )

    return call_events, presence_events
