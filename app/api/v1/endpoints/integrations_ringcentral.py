from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, require_permission
from app.db.models.integration_token import IntegrationToken
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.ringcentral_event import RingCentralEvent
from app.db.session import get_db
from app.services.audit import log_event
from app.services.ringcentral import (
    RINGCENTRAL_PROVIDER,
    RingCentralConfigurationError,
    RingCentralIntegrationError,
    RingCentralTokenPayload,
    build_ringcentral_auth_url,
    decode_ringcentral_state,
    disconnect_ringcentral,
    encode_ringcentral_state,
    exchange_code_for_tokens,
    fetch_account_identifiers,
    get_ringcentral_token_row,
    load_ringcentral_oauth_settings,
    upsert_ringcentral_token,
)


router = APIRouter(tags=["Integrations"])

class RingCentralStatusRead(BaseModel):
    connected: bool
    scope: str | None = None
    account_id: str | None = None
    extension_id: str | None = None
    expires_at: datetime | None = None


class RingCentralConnectRead(BaseModel):
    auth_url: str


class RingCentralDisconnectRead(BaseModel):
    disconnected: bool


class RingCentralWebhookIngestRead(BaseModel):
    ingested: bool
    event_id: str


def _sanitize_reason(raw_reason: str) -> str:
    normalized = "".join(
        ch if ch.isalnum() or ch == "_" else "_"
        for ch in raw_reason.strip().lower()
    )
    compact = "_".join(part for part in normalized.split("_") if part)
    return compact[:80] or "unknown_error"


def _post_connect_redirect_url(*, result: str, reason: str | None = None) -> str:
    base = (
        os.getenv("RINGCENTRAL_POST_CONNECT_REDIRECT", "").strip()
        or "https://360-encompass.com/admin-center"
    )
    payload = {"ringcentral": result}
    if reason:
        payload["reason"] = _sanitize_reason(reason)
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{urlencode(payload)}"


def _callback_redirect(*, result: str, reason: str | None = None) -> RedirectResponse:
    return RedirectResponse(
        _post_connect_redirect_url(result=result, reason=reason),
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_webhook_fields(payload: dict[str, Any]) -> dict[str, Any]:
    body_value = payload.get("body")
    body = body_value if isinstance(body_value, dict) else payload

    event_type = str(payload.get("event", "")).strip() or str(payload.get("eventType", "")).strip() or "unknown"
    rc_event_id = str(payload.get("uuid", "")).strip() or str(payload.get("eventId", "")).strip() or None
    session_id = str(body.get("telephonySessionId", "")).strip() or str(body.get("sessionId", "")).strip() or None
    call_id = str(body.get("id", "")).strip() or session_id

    parties_raw = body.get("parties")
    if isinstance(parties_raw, list):
        first_party = parties_raw[0] if parties_raw else {}
    elif isinstance(body.get("party"), dict):
        first_party = body.get("party")
    else:
        first_party = {}
    party = first_party if isinstance(first_party, dict) else {}

    from_value = party.get("from")
    to_value = party.get("to")
    from_number = None
    to_number = None
    if isinstance(from_value, dict):
        from_number = str(from_value.get("phoneNumber", "")).strip() or None
    elif isinstance(body.get("from"), dict):
        from_number = str(body["from"].get("phoneNumber", "")).strip() or None

    if isinstance(to_value, dict):
        to_number = str(to_value.get("phoneNumber", "")).strip() or None
    elif isinstance(body.get("to"), dict):
        to_number = str(body["to"].get("phoneNumber", "")).strip() or None

    disposition = None
    party_status = party.get("status")
    if isinstance(party_status, dict):
        disposition = str(party_status.get("code", "")).strip() or None
    if not disposition:
        body_status = body.get("status")
        if isinstance(body_status, dict):
            disposition = str(body_status.get("code", "")).strip() or None
        elif isinstance(body_status, str):
            disposition = body_status.strip() or None
    if not disposition:
        disposition = str(body.get("disposition", "")).strip() or None

    direction = str(party.get("direction", "")).strip() or str(body.get("direction", "")).strip() or None
    started_at = _parse_iso_datetime(party.get("startTime")) or _parse_iso_datetime(body.get("startTime"))
    ended_at = _parse_iso_datetime(party.get("endTime")) or _parse_iso_datetime(body.get("endTime"))
    account_id = (
        str(body.get("ownerId", "")).strip()
        or str(body.get("accountId", "")).strip()
        or str(payload.get("ownerId", "")).strip()
        or str(payload.get("accountId", "")).strip()
        or None
    )

    return {
        "event_type": event_type,
        "rc_event_id": rc_event_id,
        "session_id": session_id,
        "call_id": call_id,
        "from_number": from_number,
        "to_number": to_number,
        "direction": direction,
        "disposition": disposition,
        "started_at": started_at,
        "ended_at": ended_at,
        "account_id": account_id,
    }


def _validate_webhook_secret(request: Request) -> None:
    configured_secret = os.getenv("RINGCENTRAL_WEBHOOK_SECRET", "").strip()
    if not configured_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RingCentral webhook secret is not configured",
        )

    provided_secret = (
        request.headers.get("X-RingCentral-Webhook-Secret")
        or request.headers.get("X-Webhook-Secret")
        or request.query_params.get("secret")
    )
    if (provided_secret or "").strip() != configured_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid RingCentral webhook secret",
        )


def _resolve_webhook_integration_row(
    *,
    db: Session,
    organization_id: str | None,
    payload_account_id: str | None,
) -> IntegrationToken:
    if organization_id:
        row = get_ringcentral_token_row(db=db, organization_id=organization_id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="RingCentral integration is not connected",
            )
        return row

    if not payload_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="organization_id is required when webhook payload does not include accountId",
        )

    rows = db.execute(
        select(IntegrationToken).where(
            IntegrationToken.provider == RINGCENTRAL_PROVIDER,
            IntegrationToken.account_id == payload_account_id,
        )
    ).scalars().all()
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No RingCentral integration found for webhook account",
        )
    if len(rows) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Webhook account is linked to multiple organizations",
        )
    return rows[0]


def _ensure_membership_for_state(*, db: Session, organization_id: str, user_id: str) -> OrganizationMembership:
    membership = db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
    ).scalar_one_or_none()
    if not membership:
        raise RingCentralIntegrationError("state_membership_not_found", 400)
    if not membership.user or not membership.user.is_active:
        raise RingCentralIntegrationError("state_user_inactive", 401)
    return membership


@router.get("/integrations/ringcentral/status", response_model=RingCentralStatusRead)
def ringcentral_status(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("admin:integrations")),
) -> RingCentralStatusRead:
    row = get_ringcentral_token_row(db=db, organization_id=membership.organization_id)
    if not row:
        return RingCentralStatusRead(connected=False)
    return RingCentralStatusRead(
        connected=True,
        scope=row.scope,
        account_id=row.account_id,
        extension_id=row.extension_id,
        expires_at=row.expires_at,
    )


@router.post("/integrations/ringcentral/connect", response_model=RingCentralConnectRead)
def ringcentral_connect(
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("admin:integrations")),
) -> RingCentralConnectRead:
    try:
        settings = load_ringcentral_oauth_settings()
    except RingCentralConfigurationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    state = encode_ringcentral_state(
        organization_id=membership.organization_id,
        user_id=membership.user_id,
    )
    auth_url = build_ringcentral_auth_url(settings=settings, state=state)
    return RingCentralConnectRead(auth_url=auth_url)


@router.get("/integrations/ringcentral/callback")
def ringcentral_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if error:
        return _callback_redirect(
            result="error",
            reason=error_description or error,
        )

    if not code or not state:
        return _callback_redirect(result="error", reason="missing_code_or_state")

    try:
        settings = load_ringcentral_oauth_settings()
        decoded_state = decode_ringcentral_state(state)
        membership = _ensure_membership_for_state(
            db=db,
            organization_id=decoded_state["org_id"],
            user_id=decoded_state["user_id"],
        )
        token_payload = exchange_code_for_tokens(settings=settings, code=code)
        account_id, extension_id = fetch_account_identifiers(
            settings=settings,
            access_token=token_payload.access_token,
        )
        stored = upsert_ringcentral_token(
            db=db,
            organization_id=decoded_state["org_id"],
            token_payload=replace(
                token_payload,
                account_id=account_id,
                extension_id=extension_id,
            ),
        )

        log_event(
            db,
            action="integration.ringcentral.connected",
            entity_type="integration_token",
            entity_id=stored.id,
            organization_id=decoded_state["org_id"],
            actor=membership.user.email,
            metadata={
                "provider": "ringcentral",
                "account_id": stored.account_id,
                "extension_id": stored.extension_id,
                "scope": stored.scope,
            },
        )
    except RingCentralIntegrationError as exc:
        db.rollback()
        return _callback_redirect(result="error", reason=exc.detail)
    except Exception:
        db.rollback()
        return _callback_redirect(result="error", reason="unexpected_error")

    return _callback_redirect(result="connected")


@router.post("/integrations/ringcentral/disconnect", response_model=RingCentralDisconnectRead)
def ringcentral_disconnect(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("admin:integrations")),
) -> RingCentralDisconnectRead:
    disconnected = disconnect_ringcentral(
        db=db,
        organization_id=membership.organization_id,
    )
    log_event(
        db,
        action="integration.ringcentral.disconnected",
        entity_type="integration",
        entity_id=membership.organization_id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={"provider": "ringcentral", "disconnected": disconnected},
    )
    return RingCentralDisconnectRead(disconnected=disconnected)


@router.post("/integrations/ringcentral/webhook", response_model=RingCentralWebhookIngestRead)
async def ringcentral_webhook(
    request: Request,
    organization_id: str | None = Query(default=None, alias="organization_id"),
    db: Session = Depends(get_db),
) -> RingCentralWebhookIngestRead:
    _validate_webhook_secret(request)

    try:
        payload_raw = await request.json()
    except Exception:
        payload_raw = {}
    if not isinstance(payload_raw, dict):
        payload_raw = {}

    extracted = _extract_webhook_fields(payload_raw)
    row = _resolve_webhook_integration_row(
        db=db,
        organization_id=organization_id,
        payload_account_id=extracted["account_id"],
    )
    resolved_org_id = row.organization_id
    payload_account_id = extracted["account_id"]
    if row.account_id and payload_account_id and row.account_id != payload_account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Webhook account does not match organization integration",
        )

    event = RingCentralEvent(
        organization_id=resolved_org_id,
        event_type=extracted["event_type"],
        rc_event_id=extracted["rc_event_id"],
        session_id=extracted["session_id"],
        call_id=extracted["call_id"],
        from_number=extracted["from_number"],
        to_number=extracted["to_number"],
        direction=extracted["direction"],
        disposition=extracted["disposition"],
        started_at=extracted["started_at"],
        ended_at=extracted["ended_at"],
        raw_json=json.dumps(payload_raw, default=str),
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    log_event(
        db,
        action="integration.ringcentral.webhook_ingested",
        entity_type="ringcentral_event",
        entity_id=event.id,
        organization_id=resolved_org_id,
        actor="ringcentral:webhook",
        metadata={
            "event_type": event.event_type,
            "call_id": event.call_id,
            "session_id": event.session_id,
        },
    )

    return RingCentralWebhookIngestRead(ingested=True, event_id=event.id)
