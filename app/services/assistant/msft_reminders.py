from __future__ import annotations

import json
import logging
import re
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.core.time import utc_now
from app.db.models.assistant_memory_item import AssistantMemoryItem
from app.db.models.assistant_reminder import AssistantReminder
from app.db.models.ai_message import AiMessage
from app.db.models.ai_thread import AiThread
from app.db.models.organization_membership import OrganizationMembership
from app.services import microsoft_graph
from app.services.assistant.agent_registry import AgentDefinition
from app.services.assistant.tool_gateway import ToolCallResult, execute_tool
from app.services.ai_copilot import AiCopilotError, encrypt_sensitive_text
from app.services.audit import log_event


logger = logging.getLogger(__name__)

VALLEY_TODO_LIST_NAME = "Valley AI"
SAFE_MSFT_TITLE = "Valley AI Reminder"
SAFE_MSFT_BODY = "Open VEHR to view details."

_CLOCK_TIME_RE = re.compile(r"\\b(\\d{1,2})(:(\\d{2}))?\\s*(am|pm)\\b", re.IGNORECASE)

_IANA_TO_WINDOWS: dict[str, str] = {
    "UTC": "UTC",
    "Etc/UTC": "UTC",
    "America/New_York": "Eastern Standard Time",
    "America/Chicago": "Central Standard Time",
    "America/Denver": "Mountain Standard Time",
    "America/Phoenix": "US Mountain Standard Time",
    "America/Los_Angeles": "Pacific Standard Time",
    "America/Anchorage": "Alaskan Standard Time",
    "Pacific/Honolulu": "Hawaiian Standard Time",
}
_WINDOWS_TO_IANA: dict[str, str] = {windows: iana for iana, windows in _IANA_TO_WINDOWS.items()}


def message_mentions_calendar(message: str) -> bool:
    lowered = (message or "").lower()
    return "calendar" in lowered or "outlook" in lowered


def message_has_explicit_clock_time(message: str) -> bool:
    return bool(_CLOCK_TIME_RE.search(message or ""))


def due_at_is_date_only(due_at: datetime) -> bool:
    aware = due_at if due_at.tzinfo else due_at.replace(tzinfo=timezone.utc)
    return aware.timetz().hour == 0 and aware.timetz().minute == 0 and aware.timetz().second == 0 and aware.timetz().microsecond == 0


def select_reminder_channels(
    *,
    due_at: datetime,
    raw_channels: dict[str, Any] | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    raw = raw_channels if isinstance(raw_channels, dict) else {}
    allow_details = bool(raw.get("msft_allow_details")) if "msft_allow_details" in raw else False

    explicit_outlook = bool(raw.get("outlook")) or bool(raw.get("calendar"))
    explicit_todo = bool(raw.get("todo"))

    use_outlook: bool
    if explicit_outlook:
        use_outlook = True
    elif explicit_todo:
        use_outlook = False
    else:
        use_outlook = not due_at_is_date_only(due_at)

    channels: dict[str, Any] = {"in_chat": True, "msft_allow_details": allow_details}
    if use_outlook:
        channels["outlook"] = True
    else:
        channels["todo"] = True
    return channels


def channel_names(channels: dict[str, Any] | None) -> list[str]:
    if not isinstance(channels, dict):
        return ["in_chat"]
    names: list[str] = []
    for key in ("outlook", "todo", "in_chat"):
        if bool(channels.get(key)):
            names.append(key)
    return names or ["in_chat"]


def resolve_user_timezone(*, db: Session, organization_id: str, user_id: str) -> tuple[str, str]:
    """Return (iana_timezone, graph_timezone). Defaults to UTC."""
    now = utc_now()
    row = (
        db.execute(
            select(AssistantMemoryItem)
            .where(
                AssistantMemoryItem.organization_id == organization_id,
                AssistantMemoryItem.user_id == user_id,
                AssistantMemoryItem.key == "pref.timezone",
            )
            .order_by(AssistantMemoryItem.updated_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is None:
        return "UTC", "UTC"
    if row.expires_at is not None and row.expires_at <= now:
        return "UTC", "UTC"

    raw = (row.value or "").strip()
    if not raw:
        return "UTC", "UTC"

    if raw in _IANA_TO_WINDOWS:
        return raw, _IANA_TO_WINDOWS[raw]
    if raw in _WINDOWS_TO_IANA:
        return _WINDOWS_TO_IANA[raw], raw
    if raw.lower() in {"utc", "etc/utc", "gmt"}:
        return "UTC", "UTC"

    # Unknown timezone format; fall back safely.
    return "UTC", "UTC"


def _zoneinfo_or_utc(iana_tz: str) -> ZoneInfo | timezone:
    if not iana_tz or iana_tz.upper() == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(iana_tz)
    except Exception:
        return timezone.utc


def _local_datetime_string(dt: datetime, tzinfo: ZoneInfo | timezone) -> str:
    aware = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    local = aware.astimezone(tzinfo)
    return local.replace(tzinfo=None).isoformat(timespec="seconds")


def _todo_due_datetime_string(due_at: datetime, tzinfo: ZoneInfo | timezone) -> str:
    aware = due_at if due_at.tzinfo else due_at.replace(tzinfo=timezone.utc)
    local_date = aware.astimezone(tzinfo).date()
    return datetime.combine(local_date, time(9, 0, 0)).isoformat(timespec="seconds")


def _backoff_for_failure(new_attempt_count: int) -> timedelta:
    if new_attempt_count <= 1:
        return timedelta(minutes=5)
    if new_attempt_count == 2:
        return timedelta(minutes=30)
    return timedelta(hours=2)


def _ensure_status_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _mark_msft_success(*, reminder: AssistantReminder, channel: str) -> None:
    status_json = _ensure_status_json(reminder.msft_channel_status_json)
    status_json[channel] = "ok"
    reminder.msft_channel_status_json = status_json
    reminder.msft_last_error = None
    reminder.msft_next_attempt_at = None


def _mark_msft_failure(*, reminder: AssistantReminder, channel: str, error: str) -> None:
    status_json = _ensure_status_json(reminder.msft_channel_status_json)
    status_json[channel] = "failed"
    reminder.msft_channel_status_json = status_json
    reminder.msft_last_error = (error or "msft_channel_failed").strip()[:800] or "msft_channel_failed"
    new_attempt_count = int(reminder.msft_attempt_count or 0) + 1
    reminder.msft_attempt_count = new_attempt_count
    reminder.msft_next_attempt_at = utc_now() + _backoff_for_failure(new_attempt_count)


def _warning_for_channel(channel: str) -> str:
    if channel == "outlook":
        return "msft_outlook_create_failed"
    return "msft_todo_create_failed"


def _emit_msft_summary_message(
    *,
    db: Session,
    reminder: AssistantReminder,
    channel: str,
) -> None:
    if not reminder.thread_id:
        return
    thread = db.execute(
        select(AiThread).where(
            AiThread.id == reminder.thread_id,
            AiThread.organization_id == reminder.organization_id,
            AiThread.user_id == reminder.user_id,
        )
    ).scalar_one_or_none()
    if thread is None:
        return

    summary = "Created a Microsoft To Do draft for your reminder."
    if channel == "outlook":
        summary = "Created an Outlook calendar draft for your reminder."

    try:
        encrypted = encrypt_sensitive_text(summary)
    except AiCopilotError:
        logger.exception("msft_reminder_summary_encrypt_failed reminder_id=%s", reminder.id)
        return

    db.add(
        AiMessage(
            thread_id=thread.id,
            role="assistant",
            content=encrypted,
            metadata_json=json.dumps(
                {
                    "type": "assistant_msft_draft",
                    "reminder_id": reminder.id,
                    "channel": channel,
                },
                default=str,
            ),
        )
    )


def ensure_msft_artifacts_for_reminder(
    *,
    db: Session,
    tool_db: Session | None,
    reminder: AssistantReminder,
    membership: OrganizationMembership,
    agent: AgentDefinition,
    trigger: str,
    patient_id: str | None = None,
    workstation_id: str | None = None,
) -> list[str]:
    """Create Microsoft 365 artifacts for the reminder (best-effort, idempotent).

    This never raises; it updates reminder.msft_* fields and returns warnings.
    """
    tool_session = tool_db or db
    warnings: list[str] = []

    channels = reminder.channels if isinstance(reminder.channels, dict) else {}
    want_todo = bool(channels.get("todo"))
    want_outlook = bool(channels.get("outlook"))

    if not want_todo and not want_outlook:
        return warnings

    iana_tz, graph_tz = resolve_user_timezone(
        db=db,
        organization_id=reminder.organization_id,
        user_id=reminder.user_id,
    )
    tzinfo = _zoneinfo_or_utc(iana_tz)

    actor = membership.user.email if getattr(membership, "user", None) is not None else None

    if want_todo and not (reminder.msft_task_id or "").strip():
        log_event(
            tool_session,
            action="assistant_msft_channel_attempt",
            entity_type="assistant_reminder",
            entity_id=reminder.id,
            organization_id=reminder.organization_id,
            actor=actor,
            metadata={
                "channel": "todo",
                "reminder_id": reminder.id,
                "user_id": reminder.user_id,
                "trigger": trigger,
            },
        )

        payload = {
            "list_name": VALLEY_TODO_LIST_NAME,
            "title": SAFE_MSFT_TITLE,
            "body": SAFE_MSFT_BODY,
            "due_datetime": _todo_due_datetime_string(reminder.due_at, tzinfo),
            "time_zone": graph_tz,
        }

        def _executor() -> dict[str, Any]:
            try:
                task_id = microsoft_graph.create_todo_task_draft(
                    db=tool_session,
                    organization_id=reminder.organization_id,
                    user_id=reminder.user_id,
                    list_name=payload["list_name"],
                    title=payload["title"],
                    body=payload["body"],
                    due_datetime=payload["due_datetime"],
                    time_zone=payload["time_zone"],
                )
            except microsoft_graph.MicrosoftIntegrationNotConnectedError:
                raise HTTPException(status_code=409, detail="needs_m365_connect")
            return {"id": task_id}

        tool_result: ToolCallResult = execute_tool(
            db=tool_session,
            membership=membership,
            agent=agent,
            tool_id="ms.todo.task.create_draft",
            args=payload,
            patient_id=patient_id,
            workstation_id=workstation_id,
            executor=_executor,
        )

        if tool_result.status == "allowed" and tool_result.result and tool_result.result.get("id"):
            reminder.msft_task_id = str(tool_result.result.get("id"))
            _mark_msft_success(reminder=reminder, channel="todo")
            db.add(reminder)
            db.commit()
            _emit_msft_summary_message(db=db, reminder=reminder, channel="todo")

            log_event(
                tool_session,
                action="assistant_msft_channel_success",
                entity_type="assistant_reminder",
                entity_id=reminder.id,
                organization_id=reminder.organization_id,
                actor=actor,
                metadata={
                    "channel": "todo",
                    "reminder_id": reminder.id,
                    "task_id": reminder.msft_task_id,
                    "trigger": trigger,
                },
            )
        else:
            error = tool_result.error or "msft_todo_create_failed"
            _mark_msft_failure(reminder=reminder, channel="todo", error=error)
            db.add(reminder)
            db.commit()
            warnings.append(_warning_for_channel("todo"))

            log_event(
                tool_session,
                action="assistant_msft_channel_failed",
                entity_type="assistant_reminder",
                entity_id=reminder.id,
                organization_id=reminder.organization_id,
                actor=actor,
                metadata={
                    "channel": "todo",
                    "reminder_id": reminder.id,
                    "error": str(error)[:800],
                    "trigger": trigger,
                },
            )

    if want_outlook and not (reminder.msft_event_id or "").strip():
        log_event(
            tool_session,
            action="assistant_msft_channel_attempt",
            entity_type="assistant_reminder",
            entity_id=reminder.id,
            organization_id=reminder.organization_id,
            actor=actor,
            metadata={
                "channel": "outlook",
                "reminder_id": reminder.id,
                "user_id": reminder.user_id,
                "trigger": trigger,
            },
        )

        start_local = _local_datetime_string(reminder.due_at, tzinfo)
        end_local = _local_datetime_string(reminder.due_at + timedelta(minutes=15), tzinfo)
        payload = {
            "subject": SAFE_MSFT_TITLE,
            "body": SAFE_MSFT_BODY,
            "start_datetime": start_local,
            "end_datetime": end_local,
            "time_zone": graph_tz,
            "transaction_id": reminder.id,
        }

        def _executor() -> dict[str, Any]:
            try:
                event_id = microsoft_graph.create_outlook_event_draft(
                    db=tool_session,
                    organization_id=reminder.organization_id,
                    user_id=reminder.user_id,
                    subject=payload["subject"],
                    body=payload["body"],
                    start_datetime=payload["start_datetime"],
                    end_datetime=payload["end_datetime"],
                    time_zone=payload["time_zone"],
                    transaction_id=payload["transaction_id"],
                )
            except microsoft_graph.MicrosoftIntegrationNotConnectedError:
                raise HTTPException(status_code=409, detail="needs_m365_connect")
            return {"id": event_id}

        tool_result = execute_tool(
            db=tool_session,
            membership=membership,
            agent=agent,
            tool_id="ms.outlook.event.create_draft",
            args=payload,
            patient_id=patient_id,
            workstation_id=workstation_id,
            executor=_executor,
        )

        if tool_result.status == "allowed" and tool_result.result and tool_result.result.get("id"):
            reminder.msft_event_id = str(tool_result.result.get("id"))
            _mark_msft_success(reminder=reminder, channel="outlook")
            db.add(reminder)
            db.commit()
            _emit_msft_summary_message(db=db, reminder=reminder, channel="outlook")

            log_event(
                tool_session,
                action="assistant_msft_channel_success",
                entity_type="assistant_reminder",
                entity_id=reminder.id,
                organization_id=reminder.organization_id,
                actor=actor,
                metadata={
                    "channel": "outlook",
                    "reminder_id": reminder.id,
                    "event_id": reminder.msft_event_id,
                    "trigger": trigger,
                },
            )
        else:
            error = tool_result.error or "msft_outlook_create_failed"
            _mark_msft_failure(reminder=reminder, channel="outlook", error=error)
            db.add(reminder)
            db.commit()
            warnings.append(_warning_for_channel("outlook"))

            log_event(
                tool_session,
                action="assistant_msft_channel_failed",
                entity_type="assistant_reminder",
                entity_id=reminder.id,
                organization_id=reminder.organization_id,
                actor=actor,
                metadata={
                    "channel": "outlook",
                    "reminder_id": reminder.id,
                    "error": str(error)[:800],
                    "trigger": trigger,
                },
            )

    return warnings
