from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import auth_scheme, get_current_membership, require_permission
from app.core.rbac import has_permission_for_organization
from app.core.security import decode_access_token
from app.db.models.call_disposition import CallDisposition
from app.db.models.call_event import CallEvent
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.ringcentral_credential import RingCentralCredential
from app.db.models.ringcentral_event import RingCentralEvent
from app.db.models.ringcentral_subscription import RingCentralSubscription
from app.db.models.user import User
from app.db.session import get_db
from app.services.audit import log_event
from app.services.call_center_bus import call_center_event_bus, publish_event
from app.services.ringcentral_realtime import (
    RingCentralOAuthTokenPayload,
    RingCentralRealtimeError,
    build_authorization_url,
    ensure_subscription,
    exchange_authorization_code,
    extract_account_id_from_payload,
    fetch_account_and_extension,
    get_credential,
    get_subscription,
    load_ringcentral_runtime_config,
    make_state,
    normalize_webhook_events,
    parse_state,
    readback_credential,
    upsert_credential,
)


logger = logging.getLogger(__name__)
router = APIRouter(tags=["RingCentral Live"])

CALL_OVERLAY_STATUSES = {"NEW", "MISSED", "CALLED_BACK", "RESOLVED"}
ACTIVE_CALL_STATES = {"ringing", "answered", "connected", "in_progress", "on_call"}
DEV_ENV_VALUES = {"dev", "development", "local", "test"}
ALLOWED_CALLBACK_HOSTS = {
    "360-encompass.com",
    "www.360-encompass.com",
    "localhost",
    "127.0.0.1",
}


class RingCentralConnectRead(BaseModel):
    authorization_url: str
    auth_url: str


class RingCentralStatusRead(BaseModel):
    connected: bool
    organization_id: str
    user_id: str
    scope: str | None = None
    rc_account_id: str | None = None
    rc_extension_id: str | None = None
    expires_at: datetime | None = None
    # Backward compatibility for existing frontend consumers.
    account_id: str | None = None
    extension_id: str | None = None
    token_expires_at: datetime | None = None
    subscription_status: str | None = None
    subscription_expires_at: datetime | None = None


class RingCentralEnsureSubscriptionRead(BaseModel):
    status: str
    rc_subscription_id: str | None = None
    expires_at: datetime | None = None


class RingCentralDisconnectRead(BaseModel):
    ok: bool
    disconnected: bool


class CallCenterPresenceItemRead(BaseModel):
    user_id: str
    full_name: str | None = None
    email: str
    role: str
    extension_id: str | None = None
    status: str
    updated_at: datetime | None = None
    source: str


class CallCenterCallRead(BaseModel):
    call_id: str
    state: str
    disposition: str | None = None
    from_number: str | None = None
    to_number: str | None = None
    direction: str | None = None
    extension_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    last_event_at: datetime
    overlay_status: str = "NEW"
    assigned_to_user_id: str | None = None
    notes: str | None = None


class CallDispositionSnapshotRead(BaseModel):
    call_id: str
    status: str
    assigned_to_user_id: str | None = None
    notes: str | None = None
    updated_at: datetime


class CallCenterSnapshotRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    live_calls: list[CallCenterCallRead] = Field(default_factory=list, alias="liveCalls")
    dispositions: list[CallDispositionSnapshotRead] = Field(default_factory=list)
    presence: list[CallCenterPresenceItemRead]
    active_calls: list[CallCenterCallRead]
    call_log: list[CallCenterCallRead]
    subscription_status: str
    last_webhook_received_at: datetime | None = None


class CallDispositionUpdateRequest(BaseModel):
    status: str = Field(..., description="NEW, MISSED, CALLED_BACK, RESOLVED")
    assigned_to_user_id: str | None = None
    notes: str | None = None


class CallDispositionRead(BaseModel):
    call_id: str
    status: str
    assigned_to_user_id: str | None = None
    notes: str | None = None
    updated_at: datetime


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _is_dev_mode() -> bool:
    env_value = (os.getenv("APP_ENV", "").strip() or os.getenv("ENV", "").strip()).lower()
    if not env_value:
        return True
    return env_value in DEV_ENV_VALUES


def _sanitize_reason(raw_reason: str) -> str:
    normalized = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in raw_reason.strip().lower())
    compact = "_".join(part for part in normalized.split("_") if part)
    return compact[:80] or "unknown_error"


def _callback_redirect_url(*, return_to: str, connected: bool, err: str | None = None) -> str:
    parsed = urlparse(return_to)
    hostname = (parsed.hostname or "").strip().lower()
    is_localhost_port = hostname in {"localhost", "127.0.0.1"} and parsed.port is not None
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or (hostname not in ALLOWED_CALLBACK_HOSTS and not is_localhost_port)
    ):
        return_to = "https://360-encompass.com/admin-center"
    separator = "&" if "?" in return_to else "?"
    payload = {"connected": "1" if connected else "0"}
    if err and not connected:
        payload["err"] = _sanitize_reason(err)
    return f"{return_to}{separator}{urlencode(payload)}"


def _load_config_or_raise():
    try:
        return load_ringcentral_runtime_config()
    except RingCentralRealtimeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _resolve_webhook_secret(request: Request) -> str:
    return (
        request.headers.get("X-RingCentral-Webhook-Secret")
        or request.headers.get("X-Webhook-Secret")
        or request.query_params.get("secret")
        or ""
    ).strip()


def _resolve_webhook_signature(request: Request) -> str:
    return (
        request.headers.get("X-RingCentral-Signature")
        or request.headers.get("X-Webhook-Signature")
        or ""
    ).strip()


def _extract_subscription_id(payload: dict[str, Any], request: Request) -> str | None:
    for key in ["subscriptionId", "subscription_id"]:
        value = str(payload.get(key, "")).strip()
        if value:
            return value

    subscription_obj = payload.get("subscription")
    if isinstance(subscription_obj, dict):
        value = str(subscription_obj.get("id", "")).strip()
        if value:
            return value

    body = payload.get("body")
    if isinstance(body, dict):
        for key in ["subscriptionId", "subscription_id"]:
            value = str(body.get(key, "")).strip()
            if value:
                return value

    header_value = request.headers.get("X-RingCentral-Subscription-Id", "").strip()
    if header_value:
        return header_value
    return None


def _is_valid_webhook_signature(*, raw_body: bytes, shared_secret: str, signature_header: str) -> bool:
    if not signature_header:
        return True

    expected_hex = hmac.new(shared_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    expected_prefixed = f"sha256={expected_hex}"
    expected_base64 = base64.b64encode(
        hmac.new(shared_secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    ).decode("utf-8")

    provided = signature_header.strip()
    return (
        hmac.compare_digest(provided, expected_hex)
        or hmac.compare_digest(provided, expected_prefixed)
        or hmac.compare_digest(provided, expected_base64)
    )


def _resolve_webhook_org(
    *,
    db: Session,
    organization_id: str | None,
    payload_subscription_id: str | None,
    payload_account_id: str | None,
) -> str:
    if organization_id:
        return organization_id

    if payload_subscription_id:
        rows = db.execute(
            select(RingCentralSubscription).where(
                RingCentralSubscription.rc_subscription_id == payload_subscription_id
            )
        ).scalars().all()
        if len(rows) == 1:
            return rows[0].organization_id
        if len(rows) > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Webhook subscription is linked to multiple organizations",
            )

    if payload_account_id:
        rows = db.execute(
            select(RingCentralCredential).where(RingCentralCredential.rc_account_id == payload_account_id)
        ).scalars().all()
        if len(rows) == 1:
            return rows[0].organization_id
        if len(rows) > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Webhook account is linked to multiple organizations",
            )

    rows = db.execute(select(RingCentralCredential.organization_id).distinct()).all()
    if len(rows) == 1:
        return rows[0][0]
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unable to resolve organization for webhook payload",
    )


def _normalize_overlay_status(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in CALL_OVERLAY_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status must be one of NEW, MISSED, CALLED_BACK, RESOLVED",
        )
    return normalized


def _sse_message(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


def _parse_call_event_payload(raw_json: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_json)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_datetime_safe(value: Any) -> datetime | None:
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


def _resolve_stream_membership(
    *,
    db: Session,
    access_token: str | None,
    credentials: HTTPAuthorizationCredentials | None,
) -> OrganizationMembership:
    token_value = access_token or (credentials.credentials if credentials else "")
    if not token_value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing credentials")
    try:
        token_data = decode_access_token(token_value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    membership = db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == token_data.organization_id,
            OrganizationMembership.user_id == token_data.user_id,
        )
    ).scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization access denied")
    if not membership.user or not membership.user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    if not has_permission_for_organization(
        db,
        organization_id=membership.organization_id,
        role=membership.role,
        permission="calls:read",
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return membership


def _resolve_connect_membership(
    *,
    db: Session,
    access_token: str | None,
    credentials: HTTPAuthorizationCredentials | None,
    request: Request | None = None,
) -> OrganizationMembership:
    cookie_token = ""
    if request is not None:
        cookie_token = (request.cookies.get("vehr_access_token") or request.cookies.get("access_token") or "").strip()
    token_value = access_token or (credentials.credentials if credentials else "") or cookie_token
    if not token_value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing credentials")
    try:
        token_data = decode_access_token(token_value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    membership = db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == token_data.organization_id,
            OrganizationMembership.user_id == token_data.user_id,
        )
    ).scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization access denied")
    if not membership.user or not membership.user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    if not has_permission_for_organization(
        db,
        organization_id=membership.organization_id,
        role=membership.role,
        permission="admin:integrations",
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return membership


def _subscription_status_for_org(db: Session, organization_id: str) -> str:
    rows = db.execute(
        select(RingCentralSubscription).where(
            RingCentralSubscription.organization_id == organization_id
        )
    ).scalars().all()
    if not rows:
        return "MISSING"
    now = _now_utc()
    for row in rows:
        if row.status == "ACTIVE":
            if row.expires_at is None:
                return "ACTIVE"
            expiry = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
            if expiry > now:
                return "ACTIVE"
    return "EXPIRED"


def _build_call_center_snapshot(
    *,
    db: Session,
    organization_id: str,
) -> CallCenterSnapshotRead:
    cutoff = _now_utc() - timedelta(hours=12)

    call_event_rows = db.execute(
        select(CallEvent)
        .where(
            CallEvent.organization_id == organization_id,
            CallEvent.type == "call",
            CallEvent.received_at >= cutoff,
        )
        .order_by(CallEvent.received_at.desc())
        .limit(500)
    ).scalars().all()

    disposition_rows = db.execute(
        select(CallDisposition).where(CallDisposition.organization_id == organization_id)
    ).scalars().all()
    disposition_by_call_id = {row.rc_call_id: row for row in disposition_rows}

    latest_by_call_id: dict[str, CallCenterCallRead] = {}
    for row in call_event_rows:
        if not row.rc_call_id:
            continue
        if row.rc_call_id in latest_by_call_id:
            continue
        payload = _parse_call_event_payload(row.payload_json)
        disposition = disposition_by_call_id.get(row.rc_call_id)
        latest_by_call_id[row.rc_call_id] = CallCenterCallRead(
            call_id=row.rc_call_id,
            state=str(payload.get("state", "unknown")),
            disposition=str(payload.get("disposition", "")) or None,
            from_number=str(payload.get("from_number", "")) or None,
            to_number=str(payload.get("to_number", "")) or None,
            direction=str(payload.get("direction", "")) or None,
            extension_id=str(payload.get("extension_id", "")) or None,
            started_at=_parse_datetime_safe(payload.get("started_at")),
            ended_at=_parse_datetime_safe(payload.get("ended_at")),
            last_event_at=row.received_at if row.received_at.tzinfo else row.received_at.replace(tzinfo=timezone.utc),
            overlay_status=disposition.status if disposition else "NEW",
            assigned_to_user_id=disposition.assigned_to_user_id if disposition else None,
            notes=disposition.notes if disposition else None,
        )

    def _call_priority(item: CallCenterCallRead) -> int:
        state = item.state.strip().lower()
        if item.overlay_status == "MISSED":
            return 0
        if state == "ringing":
            return 1
        if state in ACTIVE_CALL_STATES and item.ended_at is None:
            return 2
        return 3

    call_log = sorted(
        latest_by_call_id.values(),
        key=lambda item: (_call_priority(item), -item.last_event_at.timestamp()),
    )
    active_calls = [row for row in call_log if row.state in ACTIVE_CALL_STATES and row.ended_at is None]
    disposition_items = sorted(
        [
            CallDispositionSnapshotRead(
                call_id=row.rc_call_id,
                status=row.status,
                assigned_to_user_id=row.assigned_to_user_id,
                notes=row.notes,
                updated_at=row.updated_at,
            )
            for row in disposition_rows
        ],
        key=lambda item: item.updated_at,
        reverse=True,
    )

    membership_rows = db.execute(
        select(OrganizationMembership, User).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == User.id,
        )
    ).all()
    credentials = db.execute(
        select(RingCentralCredential).where(RingCentralCredential.organization_id == organization_id)
    ).scalars().all()
    user_id_by_extension_id = {row.rc_extension_id: row.user_id for row in credentials if row.rc_extension_id}

    presence_event_rows = db.execute(
        select(CallEvent)
        .where(
            CallEvent.organization_id == organization_id,
            CallEvent.type == "presence",
            CallEvent.received_at >= cutoff,
        )
        .order_by(CallEvent.received_at.desc())
        .limit(500)
    ).scalars().all()
    latest_presence_by_extension: dict[str, tuple[str, datetime]] = {}
    for row in presence_event_rows:
        payload = _parse_call_event_payload(row.payload_json)
        extension_id = str(payload.get("extension_id", "")).strip()
        if not extension_id or extension_id in latest_presence_by_extension:
            continue
        status_value = str(payload.get("status", "")).strip() or "unknown"
        updated_at = row.received_at if row.received_at.tzinfo else row.received_at.replace(tzinfo=timezone.utc)
        latest_presence_by_extension[extension_id] = (status_value, updated_at)

    presence_items: list[CallCenterPresenceItemRead] = []
    for membership_row, user_row in membership_rows:
        if not has_permission_for_organization(
            db,
            organization_id=organization_id,
            role=membership_row.role,
            permission="calls:read",
        ):
            continue

        extension_id = None
        status_value = "offline" if not user_row.is_active else "available"
        updated_at = None
        source = "membership"
        for ext_id, uid in user_id_by_extension_id.items():
            if uid == user_row.id:
                extension_id = ext_id
                break
        if extension_id and extension_id in latest_presence_by_extension:
            status_value, updated_at = latest_presence_by_extension[extension_id]
            source = "ringcentral_presence"

        presence_items.append(
            CallCenterPresenceItemRead(
                user_id=user_row.id,
                full_name=user_row.full_name,
                email=user_row.email,
                role=membership_row.role,
                extension_id=extension_id,
                status=status_value,
                updated_at=updated_at,
                source=source,
            )
        )

    presence_items.sort(key=lambda row: ((row.full_name or "").lower(), row.email.lower()))
    return CallCenterSnapshotRead(
        live_calls=call_log,
        dispositions=disposition_items,
        presence=presence_items,
        active_calls=active_calls,
        call_log=call_log,
        subscription_status=_subscription_status_for_org(db, organization_id),
        last_webhook_received_at=None,
    )


@router.get("/integrations/ringcentral/connect")
def ringcentral_connect_redirect(
    request: Request,
    return_to: str | None = Query(default=None),
    access_token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(auth_scheme),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    membership = _resolve_connect_membership(
        db=db,
        access_token=access_token,
        credentials=credentials,
        request=request,
    )
    config = _load_config_or_raise()
    state = make_state(
        config=config,
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        return_to=return_to or config.default_return_to,
    )
    return RedirectResponse(
        build_authorization_url(config=config, state=state),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/integrations/ringcentral/connect", response_model=RingCentralConnectRead)
def ringcentral_connect(
    return_to: str | None = Query(default=None),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("admin:integrations")),
) -> RingCentralConnectRead:
    config = _load_config_or_raise()
    state = make_state(
        config=config,
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        return_to=return_to or config.default_return_to,
    )
    return RingCentralConnectRead(
        authorization_url=build_authorization_url(config=config, state=state),
        auth_url=build_authorization_url(config=config, state=state),
    )


@router.get("/integrations/ringcentral/callback")
def ringcentral_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    config = _load_config_or_raise()
    callback_hit = True
    state_verified = False
    state_org_id: str | None = None
    state_user_id: str | None = None
    token_exchange_ok = False
    db_upsert_ok = False
    readback_ok = False
    parsed_state = None
    logger.info(
        "ringcentral_oauth_callback callback_hit=%s state_verified=%s state_org_id=%s "
        "state_user_id=%s token_exchange_ok=%s db_upsert_ok=%s readback_ok=%s",
        callback_hit,
        state_verified,
        state_org_id,
        state_user_id,
        token_exchange_ok,
        db_upsert_ok,
        readback_ok,
    )

    try:
        if error:
            raise RingCentralRealtimeError(error_description or error or "oauth_error", 400)
        if not code or not state:
            raise RingCentralRealtimeError("missing_code_or_state", 400)

        parsed_state = parse_state(config=config, state=state)
        state_verified = True
        state_org_id = parsed_state.organization_id
        state_user_id = parsed_state.user_id

        membership = db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == parsed_state.organization_id,
                OrganizationMembership.user_id == parsed_state.user_id,
            )
        ).scalar_one_or_none()
        if not membership:
            raise RingCentralRealtimeError("state_membership_not_found", 400)

        token_payload = exchange_authorization_code(config=config, code=code)
        token_exchange_ok = True
        account_id, extension_id = fetch_account_and_extension(
            config=config,
            access_token=token_payload.access_token,
        )
        merged_payload = RingCentralOAuthTokenPayload(
            access_token=token_payload.access_token,
            refresh_token=token_payload.refresh_token,
            expires_at=token_payload.expires_at,
            scopes=token_payload.scopes,
            account_id=account_id,
            extension_id=extension_id,
        )
        saved = upsert_credential(
            db=db,
            organization_id=parsed_state.organization_id,
            user_id=parsed_state.user_id,
            token=merged_payload,
        )
        db_upsert_ok = True
        readback_credential(
            db=db,
            organization_id=parsed_state.organization_id,
            user_id=parsed_state.user_id,
        )
        readback_ok = True

        logger.info(
            "ringcentral_oauth_callback_success callback_hit=%s state_verified=%s state_org_id=%s "
            "state_user_id=%s token_exchange_ok=%s db_upsert_ok=%s readback_ok=%s",
            callback_hit,
            state_verified,
            state_org_id,
            state_user_id,
            token_exchange_ok,
            db_upsert_ok,
            readback_ok,
        )

        log_event(
            db,
            action="integration.ringcentral.connected",
            entity_type="ringcentral_credential",
            entity_id=saved.id,
            organization_id=parsed_state.organization_id,
            actor=membership.user.email,
            metadata={
                "account_id": saved.rc_account_id,
                "extension_id": saved.rc_extension_id,
            },
        )
        return RedirectResponse(
            _callback_redirect_url(return_to=parsed_state.return_to, connected=True),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except RingCentralRealtimeError as exc:
        db.rollback()
        err_code = _sanitize_reason(exc.detail)
        logger.exception(
            "ringcentral_oauth_callback_failed callback_hit=%s state_verified=%s state_org_id=%s "
            "state_user_id=%s token_exchange_ok=%s db_upsert_ok=%s readback_ok=%s err=%s",
            callback_hit,
            state_verified,
            state_org_id,
            state_user_id,
            token_exchange_ok,
            db_upsert_ok,
            readback_ok,
            err_code,
        )
        return_to = parsed_state.return_to if parsed_state else config.default_return_to
        return RedirectResponse(
            _callback_redirect_url(
                return_to=return_to,
                connected=False,
                err=err_code,
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception:
        db.rollback()
        logger.exception(
            "ringcentral_oauth_callback_failed callback_hit=%s state_verified=%s state_org_id=%s "
            "state_user_id=%s token_exchange_ok=%s db_upsert_ok=%s readback_ok=%s err=%s",
            callback_hit,
            state_verified,
            state_org_id,
            state_user_id,
            token_exchange_ok,
            db_upsert_ok,
            readback_ok,
            "unexpected_error",
        )
        return_to = parsed_state.return_to if parsed_state else config.default_return_to
        return RedirectResponse(
            _callback_redirect_url(
                return_to=return_to,
                connected=False,
                err="unexpected_error",
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.get("/integrations/ringcentral/status", response_model=RingCentralStatusRead)
def ringcentral_status(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("admin:integrations")),
) -> RingCentralStatusRead:
    row = get_credential(
        db=db,
        organization_id=membership.organization_id,
        user_id=membership.user_id,
    )
    subscription = get_subscription(
        db=db,
        organization_id=membership.organization_id,
        user_id=membership.user_id,
    )
    logger.info(
        "ringcentral_status status_check_found_credential=%s organization_id=%s user_id=%s",
        bool(row),
        membership.organization_id,
        membership.user_id,
    )
    if not row:
        return RingCentralStatusRead(
            connected=False,
            organization_id=membership.organization_id,
            user_id=membership.user_id,
            subscription_status=subscription.status if subscription else "MISSING",
            subscription_expires_at=subscription.expires_at if subscription else None,
        )
    return RingCentralStatusRead(
        connected=True,
        organization_id=membership.organization_id,
        user_id=membership.user_id,
        scope=row.scopes,
        expires_at=row.token_expires_at,
        rc_account_id=row.rc_account_id,
        rc_extension_id=row.rc_extension_id,
        account_id=row.rc_account_id,
        extension_id=row.rc_extension_id,
        token_expires_at=row.token_expires_at,
        subscription_status=subscription.status if subscription else "MISSING",
        subscription_expires_at=subscription.expires_at if subscription else None,
    )


@router.post("/integrations/ringcentral/ensure-subscription", response_model=RingCentralEnsureSubscriptionRead)
def ringcentral_ensure_subscription(
    force: bool = Query(default=False),
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("admin:integrations")),
) -> RingCentralEnsureSubscriptionRead:
    config = _load_config_or_raise()
    existing = get_subscription(
        db=db,
        organization_id=membership.organization_id,
        user_id=membership.user_id,
    )
    now = _now_utc()
    existing_is_active = False
    if existing and existing.status == "ACTIVE":
        if not existing.expires_at:
            existing_is_active = True
        else:
            expiry = existing.expires_at if existing.expires_at.tzinfo else existing.expires_at.replace(tzinfo=timezone.utc)
            existing_is_active = expiry > now

    try:
        subscription = ensure_subscription(
            db=db,
            config=config,
            organization_id=membership.organization_id,
            user_id=membership.user_id,
            force=force,
        )
    except RingCentralRealtimeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    subscription_created = force or not existing_is_active
    logger.info(
        "ringcentral_subscription subscription_created=%s rc_subscription_id=%s expires_at=%s organization_id=%s user_id=%s",
        subscription_created,
        subscription.rc_subscription_id,
        subscription.expires_at.isoformat() if subscription.expires_at else None,
        membership.organization_id,
        membership.user_id,
    )

    return RingCentralEnsureSubscriptionRead(
        status=subscription.status,
        rc_subscription_id=subscription.rc_subscription_id,
        expires_at=subscription.expires_at,
    )


@router.post("/integrations/ringcentral/disconnect", response_model=RingCentralDisconnectRead)
def ringcentral_disconnect(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("admin:integrations")),
) -> RingCentralDisconnectRead:
    disconnected = False
    row = get_credential(
        db=db,
        organization_id=membership.organization_id,
        user_id=membership.user_id,
    )
    if row:
        db.delete(row)
        disconnected = True
    sub = get_subscription(
        db=db,
        organization_id=membership.organization_id,
        user_id=membership.user_id,
    )
    if sub:
        db.delete(sub)
        disconnected = True
    db.commit()

    log_event(
        db,
        action="integration.ringcentral.disconnected",
        entity_type="ringcentral_credential",
        entity_id=membership.user_id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={"disconnected": disconnected},
    )
    return RingCentralDisconnectRead(ok=True, disconnected=disconnected)


@router.post("/webhooks/ringcentral")
@router.post("/integrations/ringcentral/webhook")
async def ringcentral_webhook(
    request: Request,
    organization_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    validation_token = request.headers.get("Validation-Token", "").strip()
    if validation_token:
        return JSONResponse(
            content={"validated": True},
            headers={"Validation-Token": validation_token},
            status_code=status.HTTP_200_OK,
        )

    config = _load_config_or_raise()
    if not config.webhook_shared_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="RINGCENTRAL_WEBHOOK_SHARED_SECRET is not configured",
        )
    shared_secret = _resolve_webhook_secret(request)
    if shared_secret != config.webhook_shared_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid RingCentral webhook secret")
    raw_body = await request.body()
    signature_header = _resolve_webhook_signature(request)
    if signature_header and not _is_valid_webhook_signature(
        raw_body=raw_body,
        shared_secret=config.webhook_shared_secret,
        signature_header=signature_header,
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid RingCentral webhook signature")

    try:
        decoded = raw_body.decode("utf-8") if raw_body else ""
        payload_raw = json.loads(decoded) if decoded else {}
    except Exception:
        payload_raw = {}
    if not isinstance(payload_raw, dict):
        payload_raw = {}

    payload_subscription_id = _extract_subscription_id(payload_raw, request)
    payload_account_id = extract_account_id_from_payload(payload_raw)
    resolved_org_id = _resolve_webhook_org(
        db=db,
        organization_id=organization_id,
        payload_subscription_id=payload_subscription_id,
        payload_account_id=payload_account_id,
    )
    event_type = str(payload_raw.get("event", "")).strip() or "unknown"
    logger.info(
        "ringcentral_webhook webhook_received=%s event_type=%s org_id=%s",
        True,
        event_type,
        resolved_org_id,
    )

    credentials_for_org = db.execute(
        select(RingCentralCredential).where(RingCentralCredential.organization_id == resolved_org_id)
    ).scalars().all()
    if payload_account_id and credentials_for_org:
        account_ids = {row.rc_account_id for row in credentials_for_org if row.rc_account_id}
        if account_ids and payload_account_id not in account_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Webhook account does not match organization integration",
            )

    call_events, presence_events = normalize_webhook_events(payload_raw)
    inserted_count = 0
    inserted_rows: list[CallEvent] = []
    legacy_rows: list[RingCentralEvent] = []

    for event in call_events:
        payload = {
            "call_id": event.rc_call_id,
            "session_id": event.session_id,
            "from_number": event.from_number,
            "to_number": event.to_number,
            "direction": event.direction,
            "state": event.state,
            "disposition": event.disposition,
            "started_at": event.started_at.isoformat() if event.started_at else None,
            "ended_at": event.ended_at.isoformat() if event.ended_at else None,
            "account_id": event.account_id,
            "extension_id": event.extension_id,
            "rc_event_id": event.rc_event_id,
            "event_filter": event.event_filter,
            "event_time": event.event_time.isoformat(),
        }
        row = CallEvent(
            organization_id=resolved_org_id,
            type="call",
            rc_call_id=event.rc_call_id,
            payload_json=json.dumps(payload),
        )
        db.add(row)
        inserted_rows.append(row)

        legacy = RingCentralEvent(
            organization_id=resolved_org_id,
            event_type=event.event_filter or "telephony_session",
            rc_event_id=event.rc_event_id,
            session_id=event.session_id,
            call_id=event.rc_call_id,
            from_number=event.from_number,
            to_number=event.to_number,
            direction=event.direction,
            disposition=event.disposition or event.state,
            started_at=event.started_at,
            ended_at=event.ended_at,
            raw_json=json.dumps(event.raw_payload, default=str),
        )
        db.add(legacy)
        legacy_rows.append(legacy)
        inserted_count += 1

    for event in presence_events:
        payload = {
            "extension_id": event.extension_id,
            "account_id": event.account_id,
            "status": event.status,
            "dnd_status": event.dnd_status,
            "rc_event_id": event.rc_event_id,
            "event_filter": event.event_filter,
            "event_time": event.event_time.isoformat(),
        }
        row = CallEvent(
            organization_id=resolved_org_id,
            type="presence",
            rc_call_id=None,
            payload_json=json.dumps(payload),
        )
        db.add(row)
        inserted_rows.append(row)
        inserted_count += 1

    if inserted_count == 0:
        row = CallEvent(
            organization_id=resolved_org_id,
            type="unknown",
            rc_call_id=None,
            payload_json=json.dumps({"payload": payload_raw}, default=str),
        )
        db.add(row)
        inserted_rows.append(row)
        inserted_count = 1

    db.flush()
    last_event_id = inserted_rows[-1].id if inserted_rows else resolved_org_id
    last_legacy_event_id = legacy_rows[-1].id if legacy_rows else None
    db.commit()

    for event in call_events:
        disposition_row = db.execute(
            select(CallDisposition).where(
                CallDisposition.organization_id == resolved_org_id,
                CallDisposition.rc_call_id == event.rc_call_id,
            )
        ).scalar_one_or_none()
        overlay_status = disposition_row.status if disposition_row else ("MISSED" if event.state == "missed" else "NEW")
        await publish_event(
            resolved_org_id,
            {
                "event": "call",
                "data": {
                    "event_type": event.event_filter or "telephony_session",
                    "session_id": event.session_id,
                    "rc_event_id": event.rc_event_id,
                    "organization_id": resolved_org_id,
                    "subscription_id": payload_subscription_id,
                    "received_at": _now_utc().isoformat(),
                    "event_filter": event.event_filter,
                    "call_id": event.rc_call_id,
                    "state": event.state,
                    "disposition": event.disposition,
                    "from_number": event.from_number,
                    "to_number": event.to_number,
                    "direction": event.direction,
                    "extension_id": event.extension_id,
                    "started_at": event.started_at.isoformat() if event.started_at else None,
                    "ended_at": event.ended_at.isoformat() if event.ended_at else None,
                    "overlay_status": overlay_status,
                    "notes": disposition_row.notes if disposition_row else None,
                    "assigned_to_user_id": disposition_row.assigned_to_user_id if disposition_row else None,
                },
                "source": "webhook",
            },
        )

    for event in presence_events:
        await publish_event(
            resolved_org_id,
            {
                "event": "presence",
                "data": {
                    "event_type": event.event_filter or "presence",
                    "organization_id": resolved_org_id,
                    "subscription_id": payload_subscription_id,
                    "received_at": _now_utc().isoformat(),
                    "event_filter": event.event_filter,
                    "extension_id": event.extension_id,
                    "status": event.status,
                    "dnd_status": event.dnd_status,
                    "event_time": event.event_time.isoformat(),
                },
                "source": "webhook",
            },
        )

    if not call_events and not presence_events:
        await publish_event(
            resolved_org_id,
            {
                "event": "unknown",
                "data": {
                    "event_type": event_type,
                    "organization_id": resolved_org_id,
                    "subscription_id": payload_subscription_id,
                    "received_at": _now_utc().isoformat(),
                },
                "source": "webhook",
            },
        )

    log_event(
        db,
        action="integration.ringcentral.webhook_ingested",
        entity_type="call_event",
        entity_id=last_event_id,
        organization_id=resolved_org_id,
        actor="ringcentral:webhook",
        metadata={
            "event_type": event_type,
            "subscription_id": payload_subscription_id,
            "payload_account_id": payload_account_id,
            "call_events": len(call_events),
            "presence_events": len(presence_events),
        },
    )

    return {
        "ingested": True,
        "count": inserted_count,
        "event_id": last_legacy_event_id or last_event_id,
        "call_event_id": last_event_id,
    }


@router.post("/webhooks/ringcentral/test-push")
async def ringcentral_test_push(
    payload: dict[str, Any],
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("admin:integrations")),
):
    if not _is_dev_mode():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not available in production")

    await publish_event(
        membership.organization_id,
        {
            "event": str(payload.get("event", "call")),
            "data": payload.get("data", payload) if isinstance(payload.get("data", payload), dict) else payload,
            "source": "api",
        },
    )
    return {"pushed": True}


@router.post("/webhooks/ringcentral/test-event")
async def ringcentral_test_event(
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("admin:integrations")),
):
    if not _is_dev_mode():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not available in production")

    now_iso = _now_utc().isoformat()
    await publish_event(
        membership.organization_id,
        {
            "event": "call",
            "data": {
                "event_type": "telephony_session",
                "organization_id": membership.organization_id,
                "call_id": f"dev-call-{membership.user_id[:8]}",
                "state": "ringing",
                "from_number": "+15550001111",
                "to_number": "+15550002222",
                "received_at": now_iso,
            },
            "source": "api",
        },
    )
    await publish_event(
        membership.organization_id,
        {
            "event": "presence",
            "data": {
                "event_type": "presence",
                "organization_id": membership.organization_id,
                "extension_id": "dev-ext-1",
                "status": "available",
                "received_at": now_iso,
            },
            "source": "api",
        },
    )
    return {"ok": True}


@router.get("/call-center/snapshot", response_model=CallCenterSnapshotRead)
def call_center_snapshot(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("calls:read")),
) -> CallCenterSnapshotRead:
    config = _load_config_or_raise()
    try:
        ensured_subscription = ensure_subscription(
            db=db,
            config=config,
            organization_id=membership.organization_id,
            user_id=membership.user_id,
            force=False,
        )
    except RingCentralRealtimeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    snapshot = _build_call_center_snapshot(
        db=db,
        organization_id=membership.organization_id,
    )
    snapshot.subscription_status = ensured_subscription.status
    return snapshot


@router.post("/call-center/calls/{call_id}/disposition", response_model=CallDispositionRead)
async def update_call_disposition(
    call_id: str,
    payload: CallDispositionUpdateRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("calls:write")),
) -> CallDispositionRead:
    status_value = _normalize_overlay_status(payload.status)
    row = db.execute(
        select(CallDisposition).where(
            CallDisposition.organization_id == membership.organization_id,
            CallDisposition.rc_call_id == call_id,
        )
    ).scalar_one_or_none()
    if row:
        row.status = status_value
        row.assigned_to_user_id = payload.assigned_to_user_id
        row.notes = payload.notes
        db.add(row)
    else:
        row = CallDisposition(
            organization_id=membership.organization_id,
            rc_call_id=call_id,
            status=status_value,
            assigned_to_user_id=payload.assigned_to_user_id,
            notes=payload.notes,
        )
        db.add(row)
    db.commit()
    db.refresh(row)

    await call_center_event_bus.publish(
        organization_id=membership.organization_id,
        event="disposition",
        data={
            "call_id": call_id,
            "status": row.status,
            "assigned_to_user_id": row.assigned_to_user_id,
            "notes": row.notes,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        },
        source="api",
    )

    log_event(
        db,
        action="call_center.disposition_updated",
        entity_type="call_disposition",
        entity_id=row.id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={"call_id": call_id, "status": row.status},
    )

    return CallDispositionRead(
        call_id=call_id,
        status=row.status,
        assigned_to_user_id=row.assigned_to_user_id,
        notes=row.notes,
        updated_at=row.updated_at,
    )


@router.get("/call-center/stream")
async def call_center_stream(
    request: Request,
    access_token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(auth_scheme),
    db: Session = Depends(get_db),
):
    membership = _resolve_stream_membership(
        db=db,
        access_token=access_token,
        credentials=credentials,
    )
    organization_id = membership.organization_id
    listener_id, queue = await call_center_event_bus.subscribe(organization_id)

    async def event_generator():
        last_fallback_check = _now_utc()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield _sse_message(str(item.get("event", "message")), item.get("data", {}))
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    now = _now_utc()
                    if now - last_fallback_check >= timedelta(seconds=60):
                        last_fallback_check = now
                        last_webhook_at = await call_center_event_bus.get_last_webhook_at(organization_id)
                        if not last_webhook_at or (now - last_webhook_at >= timedelta(seconds=45)):
                            snapshot = _build_call_center_snapshot(
                                db=db,
                                organization_id=organization_id,
                            )
                            yield _sse_message("snapshot", snapshot.model_dump(by_alias=True))
        finally:
            await call_center_event_bus.unsubscribe(organization_id, listener_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
