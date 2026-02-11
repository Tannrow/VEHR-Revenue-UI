from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, require_permission
from app.core.rbac import has_permission_for_organization
from app.core.time import utc_now
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.reception_call_workflow import ReceptionCallWorkflow
from app.db.models.ringcentral_event import RingCentralEvent
from app.db.models.task import Task
from app.db.models.user import User
from app.db.session import get_db
from app.services.audit import log_event
from app.services.teams import team_key_for_role


router = APIRouter(tags=["Reception"])

WORKFLOW_STATUS_VALUES = {
    "missed",
    "callback_attempted",
    "callback_completed",
    "voicemail_left",
    "scheduled",
    "closed",
}
ON_CALL_DISPOSITIONS = {
    "ringing",
    "answered",
    "connected",
    "onhold",
    "hold",
    "in_progress",
}


class ReceptionCallRead(BaseModel):
    id: str
    event_type: str
    rc_event_id: str | None = None
    session_id: str | None = None
    call_id: str | None = None
    from_number: str | None = None
    to_number: str | None = None
    direction: str | None = None
    disposition: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime
    workflow_status: str | None = None
    note: str | None = None
    handled_by_user_id: str | None = None
    handled_by_name: str | None = None
    followup_task_id: str | None = None


class ReceptionCallWorkflowUpdateRequest(BaseModel):
    workflow_status: str
    note: str | None = None


class ReceptionCallWorkflowRead(BaseModel):
    id: str
    ringcentral_event_id: str
    workflow_status: str
    note: str | None = None
    handled_by_user_id: str | None = None
    followup_task_id: str | None = None
    updated_at: datetime


class ReceptionFollowupRequest(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    due_at: datetime | None = None
    note: str | None = None


class ReceptionFollowupRead(BaseModel):
    task_id: str
    ringcentral_event_id: str
    workflow_id: str


class ReceptionPresenceItemRead(BaseModel):
    user_id: str
    full_name: str | None = None
    email: str
    role: str
    status: str
    source: str


class ReceptionPresenceRead(BaseModel):
    items: list[ReceptionPresenceItemRead]


def _normalize_call_key(event: RingCentralEvent) -> str:
    return event.call_id or event.session_id or event.id


def _normalize_workflow_status(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in WORKFLOW_STATUS_VALUES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"workflow_status must be one of: {', '.join(sorted(WORKFLOW_STATUS_VALUES))}",
        )
    return normalized


def _get_event_or_404(*, db: Session, organization_id: str, event_id: str) -> RingCentralEvent:
    row = db.execute(
        select(RingCentralEvent).where(
            RingCentralEvent.organization_id == organization_id,
            RingCentralEvent.id == event_id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call event not found")
    return row


def _workflow_for_event(
    *,
    db: Session,
    organization_id: str,
    event_id: str,
) -> ReceptionCallWorkflow | None:
    return db.execute(
        select(ReceptionCallWorkflow).where(
            ReceptionCallWorkflow.organization_id == organization_id,
            ReceptionCallWorkflow.ringcentral_event_id == event_id,
        )
    ).scalar_one_or_none()


def _serialize_call(
    *,
    event: RingCentralEvent,
    workflow: ReceptionCallWorkflow | None,
    user_name_by_id: dict[str, str],
) -> ReceptionCallRead:
    return ReceptionCallRead(
        id=event.id,
        event_type=event.event_type,
        rc_event_id=event.rc_event_id,
        session_id=event.session_id,
        call_id=event.call_id,
        from_number=event.from_number,
        to_number=event.to_number,
        direction=event.direction,
        disposition=event.disposition,
        started_at=event.started_at,
        ended_at=event.ended_at,
        created_at=event.created_at,
        workflow_status=workflow.workflow_status if workflow else None,
        note=workflow.note if workflow else None,
        handled_by_user_id=workflow.handled_by_user_id if workflow else None,
        handled_by_name=user_name_by_id.get(workflow.handled_by_user_id or "") if workflow else None,
        followup_task_id=workflow.followup_task_id if workflow else None,
    )


def _ensure_task_write_permission(*, db: Session, membership: OrganizationMembership) -> None:
    can_write_self = has_permission_for_organization(
        db,
        organization_id=membership.organization_id,
        role=membership.role,
        permission="tasks:write_self",
    )
    if not can_write_self:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to create follow-up tasks",
        )


@router.get("/reception/calls", response_model=list[ReceptionCallRead])
def list_reception_calls(
    since: datetime | None = Query(default=None),
    disposition: str | None = Query(default=None),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("calls:read")),
) -> list[ReceptionCallRead]:
    filters = [RingCentralEvent.organization_id == membership.organization_id]
    if since is not None:
        filters.append(RingCentralEvent.created_at >= since)

    events = db.execute(
        select(RingCentralEvent)
        .where(*filters)
        .order_by(RingCentralEvent.created_at.desc())
        .limit(500)
    ).scalars().all()

    workflow_rows = db.execute(
        select(ReceptionCallWorkflow, RingCentralEvent)
        .join(
            RingCentralEvent,
            RingCentralEvent.id == ReceptionCallWorkflow.ringcentral_event_id,
        )
        .where(ReceptionCallWorkflow.organization_id == membership.organization_id)
    ).all()

    workflow_by_call_key: dict[str, ReceptionCallWorkflow] = {}
    for workflow_row, event_row in workflow_rows:
        key = _normalize_call_key(event_row)
        existing = workflow_by_call_key.get(key)
        if not existing or existing.updated_at < workflow_row.updated_at:
            workflow_by_call_key[key] = workflow_row

    handled_user_ids = sorted(
        {
            row.handled_by_user_id
            for row, _event in workflow_rows
            if row.handled_by_user_id
        }
    )
    user_name_by_id: dict[str, str] = {}
    if handled_user_ids:
        users = db.execute(
            select(User.id, User.full_name, User.email).where(User.id.in_(handled_user_ids))
        ).all()
        user_name_by_id = {
            user_id: (full_name or email)
            for user_id, full_name, email in users
        }

    normalized_filter = disposition.strip().lower() if disposition else None
    seen_keys: set[str] = set()
    rows: list[ReceptionCallRead] = []
    for event_row in events:
        key = _normalize_call_key(event_row)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        workflow = workflow_by_call_key.get(key)
        serialized = _serialize_call(
            event=event_row,
            workflow=workflow,
            user_name_by_id=user_name_by_id,
        )
        if normalized_filter:
            call_disposition = (serialized.disposition or "").strip().lower()
            if call_disposition != normalized_filter:
                continue
        rows.append(serialized)
    return rows


@router.patch("/reception/calls/{call_event_id}/workflow", response_model=ReceptionCallWorkflowRead)
def update_reception_call_workflow(
    call_event_id: str,
    payload: ReceptionCallWorkflowUpdateRequest,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("calls:write")),
) -> ReceptionCallWorkflowRead:
    event_row = _get_event_or_404(
        db=db,
        organization_id=membership.organization_id,
        event_id=call_event_id,
    )
    workflow_status = _normalize_workflow_status(payload.workflow_status)
    workflow = _workflow_for_event(
        db=db,
        organization_id=membership.organization_id,
        event_id=event_row.id,
    )
    if workflow:
        workflow.workflow_status = workflow_status
        workflow.note = payload.note
        workflow.handled_by_user_id = membership.user_id
        db.add(workflow)
    else:
        workflow = ReceptionCallWorkflow(
            organization_id=membership.organization_id,
            ringcentral_event_id=event_row.id,
            workflow_status=workflow_status,
            note=payload.note,
            handled_by_user_id=membership.user_id,
            followup_task_id=None,
        )
        db.add(workflow)

    db.commit()
    db.refresh(workflow)

    log_event(
        db,
        action="reception.call.workflow_updated",
        entity_type="ringcentral_event",
        entity_id=event_row.id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={
            "workflow_status": workflow.workflow_status,
            "handled_by_user_id": membership.user_id,
        },
    )

    return ReceptionCallWorkflowRead(
        id=workflow.id,
        ringcentral_event_id=workflow.ringcentral_event_id,
        workflow_status=workflow.workflow_status,
        note=workflow.note,
        handled_by_user_id=workflow.handled_by_user_id,
        followup_task_id=workflow.followup_task_id,
        updated_at=workflow.updated_at,
    )


@router.post("/reception/calls/{call_event_id}/followup", response_model=ReceptionFollowupRead)
def create_reception_followup_task(
    call_event_id: str,
    payload: ReceptionFollowupRequest,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("calls:write")),
) -> ReceptionFollowupRead:
    _ensure_task_write_permission(db=db, membership=membership)

    event_row = _get_event_or_404(
        db=db,
        organization_id=membership.organization_id,
        event_id=call_event_id,
    )
    default_title = f"Call follow-up: {event_row.from_number or 'Unknown caller'}"
    title_value = payload.title.strip() if payload.title else default_title
    if not title_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="title cannot be empty")

    task = Task(
        organization_id=membership.organization_id,
        title=title_value,
        description=payload.note or f"Follow-up for call event {event_row.id}",
        status="open",
        priority="normal",
        due_at=payload.due_at,
        completed_at=None,
        created_by_user_id=membership.user_id,
        assigned_to_user_id=membership.user_id,
        assigned_team_id=team_key_for_role(membership.role),
        related_type="call",
        related_id=event_row.id,
        tags_json=json.dumps(["call", "reception"]),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    workflow = _workflow_for_event(
        db=db,
        organization_id=membership.organization_id,
        event_id=event_row.id,
    )
    if workflow:
        workflow.followup_task_id = task.id
        workflow.handled_by_user_id = membership.user_id
        if payload.note is not None:
            workflow.note = payload.note
        db.add(workflow)
    else:
        workflow = ReceptionCallWorkflow(
            organization_id=membership.organization_id,
            ringcentral_event_id=event_row.id,
            workflow_status="callback_attempted",
            note=payload.note,
            handled_by_user_id=membership.user_id,
            followup_task_id=task.id,
        )
        db.add(workflow)

    db.commit()
    db.refresh(workflow)

    log_event(
        db,
        action="task.created",
        entity_type="task",
        entity_id=task.id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={
            "actor_user_id": membership.user_id,
            "task_id": task.id,
            "related_type": task.related_type,
            "related_id": task.related_id,
        },
    )
    log_event(
        db,
        action="reception.call.followup_created",
        entity_type="ringcentral_event",
        entity_id=event_row.id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={
            "workflow_id": workflow.id,
            "task_id": task.id,
        },
    )

    return ReceptionFollowupRead(
        task_id=task.id,
        ringcentral_event_id=event_row.id,
        workflow_id=workflow.id,
    )


@router.get("/reception/presence", response_model=ReceptionPresenceRead)
def reception_presence(
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("calls:read")),
) -> ReceptionPresenceRead:
    membership_rows = db.execute(
        select(OrganizationMembership, User).where(
            OrganizationMembership.organization_id == membership.organization_id,
            OrganizationMembership.user_id == User.id,
        )
    ).all()

    recent_cutoff = utc_now().replace(tzinfo=timezone.utc) - timedelta(minutes=15)
    workflow_rows = db.execute(
        select(ReceptionCallWorkflow, RingCentralEvent)
        .join(
            RingCentralEvent,
            RingCentralEvent.id == ReceptionCallWorkflow.ringcentral_event_id,
        )
        .where(
            ReceptionCallWorkflow.organization_id == membership.organization_id,
            ReceptionCallWorkflow.handled_by_user_id.is_not(None),
        )
        .order_by(ReceptionCallWorkflow.updated_at.desc())
    ).all()

    latest_workflow_by_user: dict[str, tuple[ReceptionCallWorkflow, RingCentralEvent]] = {}
    for workflow_row, event_row in workflow_rows:
        if not workflow_row.handled_by_user_id:
            continue
        if workflow_row.handled_by_user_id not in latest_workflow_by_user:
            latest_workflow_by_user[workflow_row.handled_by_user_id] = (workflow_row, event_row)

    items: list[ReceptionPresenceItemRead] = []
    for membership_row, user_row in membership_rows:
        if not has_permission_for_organization(
            db,
            organization_id=membership.organization_id,
            role=membership_row.role,
            permission="calls:read",
        ):
            continue
        if not user_row.is_active:
            status_value = "offline"
            source = "membership"
        else:
            status_value = "available"
            source = "membership"
            latest = latest_workflow_by_user.get(user_row.id)
            if latest:
                workflow_row, event_row = latest
                updated_at = workflow_row.updated_at
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                if updated_at >= recent_cutoff:
                    disposition = (event_row.disposition or "").strip().lower()
                    if disposition in ON_CALL_DISPOSITIONS:
                        status_value = "on_call"
                        source = "ringcentral_event"

        items.append(
            ReceptionPresenceItemRead(
                user_id=user_row.id,
                full_name=user_row.full_name,
                email=user_row.email,
                role=membership_row.role,
                status=status_value,
                source=source,
            )
        )

    items.sort(key=lambda row: ((row.full_name or "").lower(), row.email.lower()))
    return ReceptionPresenceRead(items=items)
