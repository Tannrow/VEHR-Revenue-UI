from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership
from app.core.rbac import has_permission_for_organization, normalize_role_key
from app.core.time import utc_now
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.task import Task
from app.db.models.user import User
from app.db.session import get_db
from app.services.audit import log_event
from app.services.teams import TEAM_UNASSIGNED, team_key_for_role, team_label


router = APIRouter(tags=["Tasks"])

TASK_STATUS_VALUES = {"open", "in_progress", "done", "canceled"}
TASK_PRIORITY_VALUES = {"low", "normal", "high", "urgent"}
TASK_SCOPE_VALUES = {"self", "team", "all"}
TASK_DUE_FILTER_VALUES = {"today", "overdue", "week", "later", "none"}
TASK_MATRIX_BUCKETS = ("overdue", "today", "next7", "later", "no_due")


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


TASKS_RECEPTIONIST_SELF_ONLY = _is_truthy(
    os.getenv("TASKS_RECEPTIONIST_SELF_ONLY", "true")
)


class TaskRead(BaseModel):
    id: str
    organization_id: str
    title: str
    description: str | None = None
    status: str
    priority: str
    due_at: datetime | None = None
    completed_at: datetime | None = None
    created_by_user_id: str
    assigned_to_user_id: str | None = None
    assigned_to_user_name: str | None = None
    assigned_team_id: str | None = None
    assigned_team_label: str | None = None
    related_type: str | None = None
    related_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    items: list[TaskRead]
    total: int
    limit: int
    offset: int
    counts: dict[str, int]


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    priority: str = "normal"
    due_at: datetime | None = None
    assigned_to_user_id: str | None = None
    assigned_team_id: str | None = None
    related_type: str | None = None
    related_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class TaskUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    due_at: datetime | None = None
    assigned_to_user_id: str | None = None
    assigned_team_id: str | None = None
    related_type: str | None = None
    related_id: str | None = None
    tags: list[str] | None = None


class TaskBulkRequest(BaseModel):
    task_ids: list[str] = Field(min_length=1)
    action: Literal["complete", "assign", "due_date"]
    assigned_to_user_id: str | None = None
    assigned_team_id: str | None = None
    due_at: datetime | None = None


class TaskBulkResponse(BaseModel):
    updated_task_ids: list[str]
    action: str
    updated_count: int


class TaskCalendarItemRead(BaseModel):
    id: str
    title: str
    due_at: datetime
    status: str
    priority: str
    assigned_to_user_id: str | None = None
    assigned_to_user_name: str | None = None


class TaskCalendarDayRead(BaseModel):
    day: str
    count: int
    items: list[TaskCalendarItemRead]


class TaskCalendarResponse(BaseModel):
    start: datetime
    end: datetime
    days: list[TaskCalendarDayRead]


class TaskMatrixBucketRead(BaseModel):
    count: int
    sample_task_ids: list[str]


class TaskMatrixRowRead(BaseModel):
    group_key: str
    group_label: str
    buckets: dict[str, TaskMatrixBucketRead]


class TaskMatrixResponse(BaseModel):
    scope: str
    group_by: str
    rows: list[TaskMatrixRowRead]


def _serialize_tags(tags: list[str] | None) -> str:
    if not tags:
        return "[]"
    cleaned = sorted({item.strip() for item in tags if item and item.strip()})
    return json.dumps(cleaned)


def _parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if isinstance(item, str)]


def _now_utc() -> datetime:
    return utc_now().replace(tzinfo=timezone.utc)


def _normalize_start_of_day(value: datetime) -> datetime:
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.replace(hour=0, minute=0, second=0, microsecond=0)


def _due_bucket(*, due_at: datetime | None, now: datetime) -> str:
    if due_at is None:
        return "no_due"
    due = due_at if due_at.tzinfo else due_at.replace(tzinfo=timezone.utc)
    start_today = _normalize_start_of_day(now)
    end_today = start_today + timedelta(days=1)
    if due < start_today:
        return "overdue"
    if start_today <= due < end_today:
        return "today"
    if due < (start_today + timedelta(days=8)):
        return "next7"
    return "later"


def _has_task_permission(
    db: Session,
    *,
    membership: OrganizationMembership,
    permission: str,
) -> bool:
    return has_permission_for_organization(
        db,
        organization_id=membership.organization_id,
        role=membership.role,
        permission=permission,
    )


def _validate_scope(
    db: Session,
    *,
    membership: OrganizationMembership,
    scope: str,
) -> None:
    if scope not in TASK_SCOPE_VALUES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scope")
    if scope == "all":
        if not _has_task_permission(db, membership=membership, permission="tasks:read_all"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return
    if scope == "team":
        if not (
            _has_task_permission(db, membership=membership, permission="tasks:read_team")
            or _has_task_permission(db, membership=membership, permission="tasks:read_all")
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return
    if not (
        _has_task_permission(db, membership=membership, permission="tasks:read_self")
        or _has_task_permission(db, membership=membership, permission="tasks:read_team")
        or _has_task_permission(db, membership=membership, permission="tasks:read_all")
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


def _organization_memberships(db: Session, *, organization_id: str) -> list[OrganizationMembership]:
    return db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id
        )
    ).scalars().all()


def _team_user_ids(
    db: Session,
    *,
    organization_id: str,
    team_key: str,
) -> set[str]:
    member_ids: set[str] = set()
    for row in _organization_memberships(db, organization_id=organization_id):
        if team_key_for_role(row.role) == team_key:
            member_ids.add(row.user_id)
    return member_ids


def _scope_predicates(
    db: Session,
    *,
    membership: OrganizationMembership,
    scope: str,
) -> list:
    if scope == "all":
        return []
    if scope == "self":
        return [
            or_(
                Task.created_by_user_id == membership.user_id,
                Task.assigned_to_user_id == membership.user_id,
            )
        ]

    team_key = team_key_for_role(membership.role)
    team_users = _team_user_ids(
        db,
        organization_id=membership.organization_id,
        team_key=team_key,
    )
    clauses = [Task.assigned_team_id == team_key]
    if team_users:
        clauses.append(Task.assigned_to_user_id.in_(team_users))
        clauses.append(Task.created_by_user_id.in_(team_users))
    return [or_(*clauses)]


def _assignee_user_map(db: Session, tasks: list[Task]) -> dict[str, str]:
    user_ids = sorted({row.assigned_to_user_id for row in tasks if row.assigned_to_user_id})
    if not user_ids:
        return {}
    rows = db.execute(
        select(User.id, User.full_name, User.email).where(User.id.in_(user_ids))
    ).all()
    mapped: dict[str, str] = {}
    for user_id, full_name, email in rows:
        mapped[user_id] = full_name or email
    return mapped


def _task_to_read(task: Task, assignee_map: dict[str, str]) -> TaskRead:
    team_id = task.assigned_team_id
    return TaskRead(
        id=task.id,
        organization_id=task.organization_id,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        due_at=task.due_at,
        completed_at=task.completed_at,
        created_by_user_id=task.created_by_user_id,
        assigned_to_user_id=task.assigned_to_user_id,
        assigned_to_user_name=assignee_map.get(task.assigned_to_user_id or ""),
        assigned_team_id=team_id,
        assigned_team_label=team_label(team_id) if team_id else None,
        related_type=task.related_type,
        related_id=task.related_id,
        tags=_parse_tags(task.tags_json),
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _validate_status(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in TASK_STATUS_VALUES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
    return normalized


def _validate_priority(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in TASK_PRIORITY_VALUES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid priority")
    return normalized


def _validate_assignee_membership(
    db: Session,
    *,
    organization_id: str,
    user_id: str | None,
) -> str | None:
    if not user_id:
        return None
    match = db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
    ).scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid assignee for organization")
    return user_id


def _assignee_team_key(
    db: Session,
    *,
    organization_id: str,
    assigned_to_user_id: str | None,
    assigned_team_id: str | None,
) -> str | None:
    if assigned_team_id:
        return assigned_team_id
    if not assigned_to_user_id:
        return None
    membership = db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == assigned_to_user_id,
        )
    ).scalar_one_or_none()
    if not membership:
        return None
    return team_key_for_role(membership.role)


def _task_in_team_context(
    db: Session,
    *,
    membership: OrganizationMembership,
    task: Task,
) -> bool:
    team_key = team_key_for_role(membership.role)
    if task.assigned_team_id and task.assigned_team_id == team_key:
        return True

    team_users = _team_user_ids(
        db,
        organization_id=membership.organization_id,
        team_key=team_key,
    )
    return (
        (task.assigned_to_user_id in team_users)
        or (task.created_by_user_id in team_users)
    )


def _can_read_task(
    db: Session,
    *,
    membership: OrganizationMembership,
    task: Task,
) -> bool:
    if _has_task_permission(db, membership=membership, permission="tasks:read_all"):
        return True
    if _has_task_permission(db, membership=membership, permission="tasks:read_team"):
        if _task_in_team_context(db, membership=membership, task=task):
            return True
    if _has_task_permission(db, membership=membership, permission="tasks:read_self"):
        return (
            task.created_by_user_id == membership.user_id
            or task.assigned_to_user_id == membership.user_id
        )
    return False


def _can_write_task(
    db: Session,
    *,
    membership: OrganizationMembership,
    task: Task,
) -> bool:
    if _has_task_permission(db, membership=membership, permission="tasks:read_all"):
        if _has_task_permission(db, membership=membership, permission="tasks:write_self") or _has_task_permission(
            db, membership=membership, permission="tasks:assign"
        ):
            return True
    if _has_task_permission(db, membership=membership, permission="tasks:read_team"):
        if _task_in_team_context(db, membership=membership, task=task):
            if _has_task_permission(db, membership=membership, permission="tasks:write_self") or _has_task_permission(
                db, membership=membership, permission="tasks:assign"
            ):
                return True
    if _has_task_permission(db, membership=membership, permission="tasks:write_self"):
        return (
            task.created_by_user_id == membership.user_id
            or task.assigned_to_user_id == membership.user_id
        )
    return False


def _ensure_write_create_access(
    db: Session,
    *,
    membership: OrganizationMembership,
    assigned_to_user_id: str | None,
    assigned_team_id: str | None,
) -> None:
    has_write_self = _has_task_permission(db, membership=membership, permission="tasks:write_self")
    has_assign = _has_task_permission(db, membership=membership, permission="tasks:assign")

    assigning_elsewhere = (
        (assigned_to_user_id is not None and assigned_to_user_id != membership.user_id)
        or (assigned_team_id is not None and assigned_team_id != team_key_for_role(membership.role))
    )

    if assigning_elsewhere and not has_assign:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Assignment requires tasks:assign")

    if not has_write_self and not has_assign:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    if (
        TASKS_RECEPTIONIST_SELF_ONLY
        and normalize_role_key(membership.role) == "receptionist"
        and assigned_to_user_id is not None
        and assigned_to_user_id != membership.user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Receptionist tasks must stay self-assigned",
        )


def _ensure_assignment_update_access(
    db: Session,
    *,
    membership: OrganizationMembership,
    current_task: Task,
    next_assigned_to_user_id: str | None,
    next_assigned_team_id: str | None,
) -> None:
    current_assignee = current_task.assigned_to_user_id
    current_team = current_task.assigned_team_id
    assigning_elsewhere = (
        next_assigned_to_user_id != current_assignee
        or next_assigned_team_id != current_team
    )
    if not assigning_elsewhere:
        return

    if not _has_task_permission(db, membership=membership, permission="tasks:assign"):
        if next_assigned_to_user_id and next_assigned_to_user_id != membership.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Assignment requires tasks:assign")
        if next_assigned_team_id and next_assigned_team_id != team_key_for_role(membership.role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Assignment requires tasks:assign")

    if (
        TASKS_RECEPTIONIST_SELF_ONLY
        and normalize_role_key(membership.role) == "receptionist"
        and next_assigned_to_user_id is not None
        and next_assigned_to_user_id != membership.user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Receptionist tasks must stay self-assigned",
        )


def _apply_due_filter(filters: list, due_filter: str, now: datetime) -> None:
    start_today = _normalize_start_of_day(now)
    start_tomorrow = start_today + timedelta(days=1)
    next_week = start_today + timedelta(days=8)
    if due_filter == "today":
        filters.append(and_(Task.due_at >= start_today, Task.due_at < start_tomorrow))
    elif due_filter == "overdue":
        filters.append(Task.due_at < start_today)
        filters.append(Task.status.in_(("open", "in_progress")))
    elif due_filter == "week":
        filters.append(and_(Task.due_at >= start_today, Task.due_at < next_week))
    elif due_filter == "later":
        filters.append(Task.due_at >= next_week)
    elif due_filter == "none":
        filters.append(Task.due_at.is_(None))


def _get_org_task_or_404(
    db: Session,
    *,
    organization_id: str,
    task_id: str,
) -> Task:
    row = db.execute(
        select(Task).where(
            Task.organization_id == organization_id,
            Task.id == task_id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return row


@router.get("/tasks", response_model=TaskListResponse)
def list_tasks(
    scope: str = Query(default="self"),
    statuses: list[str] | None = Query(default=None, alias="status"),
    due: str | None = Query(default=None),
    assigned_to: str | None = Query(default=None),
    team_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
) -> TaskListResponse:
    _validate_scope(db, membership=membership, scope=scope)
    now = _now_utc()

    filters = [Task.organization_id == membership.organization_id]
    filters.extend(_scope_predicates(db, membership=membership, scope=scope))

    if statuses:
        normalized = [_validate_status(item) for item in statuses]
        filters.append(Task.status.in_(normalized))

    if due:
        due_filter = due.strip().lower()
        if due_filter not in TASK_DUE_FILTER_VALUES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid due filter")
        _apply_due_filter(filters, due_filter, now)

    if assigned_to:
        if assigned_to == "me":
            filters.append(Task.assigned_to_user_id == membership.user_id)
        else:
            filters.append(Task.assigned_to_user_id == assigned_to)

    if team_id:
        filters.append(Task.assigned_team_id == team_id)

    if search and search.strip():
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                Task.title.ilike(pattern),
                Task.description.ilike(pattern),
            )
        )

    total = db.execute(
        select(func.count(Task.id)).where(*filters)
    ).scalar_one()

    rows = db.execute(
        select(Task)
        .where(*filters)
        .order_by(Task.due_at.is_(None), Task.due_at.asc(), Task.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).scalars().all()

    status_rows = db.execute(
        select(Task.status, func.count(Task.id)).where(*filters).group_by(Task.status)
    ).all()
    counts = {"total": int(total)}
    for task_status, count in status_rows:
        counts[str(task_status)] = int(count)

    assignee_map = _assignee_user_map(db, rows)
    return TaskListResponse(
        items=[_task_to_read(row, assignee_map) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
        counts=counts,
    )


@router.post("/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreateRequest,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
) -> TaskRead:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="title is required")

    assigned_to_user_id = _validate_assignee_membership(
        db,
        organization_id=membership.organization_id,
        user_id=payload.assigned_to_user_id,
    )
    _ensure_write_create_access(
        db,
        membership=membership,
        assigned_to_user_id=assigned_to_user_id,
        assigned_team_id=payload.assigned_team_id,
    )
    priority_value = _validate_priority(payload.priority)
    assigned_team_id = _assignee_team_key(
        db,
        organization_id=membership.organization_id,
        assigned_to_user_id=assigned_to_user_id,
        assigned_team_id=payload.assigned_team_id,
    )

    task = Task(
        organization_id=membership.organization_id,
        title=title,
        description=payload.description,
        status="open",
        priority=priority_value,
        due_at=payload.due_at,
        completed_at=None,
        created_by_user_id=membership.user_id,
        assigned_to_user_id=assigned_to_user_id,
        assigned_team_id=assigned_team_id,
        related_type=payload.related_type,
        related_id=payload.related_id,
        tags_json=_serialize_tags(payload.tags),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

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
            "status": task.status,
            "priority": task.priority,
            "assigned_to_user_id": task.assigned_to_user_id,
            "assigned_team_id": task.assigned_team_id,
        },
    )

    if task.assigned_to_user_id or task.assigned_team_id:
        log_event(
            db,
            action="task.assigned",
            entity_type="task",
            entity_id=task.id,
            organization_id=membership.organization_id,
            actor=membership.user.email,
            metadata={
                "actor_user_id": membership.user_id,
                "task_id": task.id,
                "assigned_to_user_id": task.assigned_to_user_id,
                "assigned_team_id": task.assigned_team_id,
            },
        )

    assignee_map = _assignee_user_map(db, [task])
    return _task_to_read(task, assignee_map)


@router.get("/tasks/{task_id}", response_model=TaskRead)
def get_task(
    task_id: str = Path(..., pattern=r"^[0-9a-fA-F-]{36}$"),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
) -> TaskRead:
    task = _get_org_task_or_404(db, organization_id=membership.organization_id, task_id=task_id)
    if not _can_read_task(db, membership=membership, task=task):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    assignee_map = _assignee_user_map(db, [task])
    return _task_to_read(task, assignee_map)


@router.patch("/tasks/{task_id}", response_model=TaskRead)
def update_task(
    payload: TaskUpdateRequest,
    task_id: str = Path(..., pattern=r"^[0-9a-fA-F-]{36}$"),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
) -> TaskRead:
    task = _get_org_task_or_404(db, organization_id=membership.organization_id, task_id=task_id)
    if not _can_write_task(db, membership=membership, task=task):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    next_assigned_to_user_id = (
        _validate_assignee_membership(
            db,
            organization_id=membership.organization_id,
            user_id=payload.assigned_to_user_id,
        )
        if payload.assigned_to_user_id is not None
        else task.assigned_to_user_id
    )
    next_assigned_team_id = (
        _assignee_team_key(
            db,
            organization_id=membership.organization_id,
            assigned_to_user_id=next_assigned_to_user_id,
            assigned_team_id=payload.assigned_team_id,
        )
        if (payload.assigned_to_user_id is not None or payload.assigned_team_id is not None)
        else task.assigned_team_id
    )

    _ensure_assignment_update_access(
        db,
        membership=membership,
        current_task=task,
        next_assigned_to_user_id=next_assigned_to_user_id,
        next_assigned_team_id=next_assigned_team_id,
    )

    changed_fields: dict[str, str | None] = {}

    if payload.title is not None:
        next_title = payload.title.strip()
        if not next_title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="title cannot be empty")
        if next_title != task.title:
            changed_fields["title"] = next_title
            task.title = next_title

    if payload.description is not None and payload.description != task.description:
        task.description = payload.description
        changed_fields["description"] = payload.description

    if payload.priority is not None:
        priority_value = _validate_priority(payload.priority)
        if priority_value != task.priority:
            task.priority = priority_value
            changed_fields["priority"] = priority_value

    if payload.status is not None:
        status_value = _validate_status(payload.status)
        if status_value != task.status:
            task.status = status_value
            changed_fields["status"] = status_value
            if status_value == "done":
                task.completed_at = _now_utc()
            else:
                task.completed_at = None

    if payload.due_at is not None and payload.due_at != task.due_at:
        task.due_at = payload.due_at
        changed_fields["due_at"] = payload.due_at.isoformat() if payload.due_at else None

    if payload.related_type is not None and payload.related_type != task.related_type:
        task.related_type = payload.related_type
        changed_fields["related_type"] = payload.related_type

    if payload.related_id is not None and payload.related_id != task.related_id:
        task.related_id = payload.related_id
        changed_fields["related_id"] = payload.related_id

    if payload.tags is not None:
        next_tags_json = _serialize_tags(payload.tags)
        if next_tags_json != task.tags_json:
            task.tags_json = next_tags_json
            changed_fields["tags"] = ",".join(_parse_tags(next_tags_json))

    assignment_changed = (
        next_assigned_to_user_id != task.assigned_to_user_id
        or next_assigned_team_id != task.assigned_team_id
    )
    if assignment_changed:
        task.assigned_to_user_id = next_assigned_to_user_id
        task.assigned_team_id = next_assigned_team_id
        changed_fields["assigned_to_user_id"] = next_assigned_to_user_id
        changed_fields["assigned_team_id"] = next_assigned_team_id

    if not changed_fields:
        assignee_map = _assignee_user_map(db, [task])
        return _task_to_read(task, assignee_map)

    db.add(task)
    db.commit()
    db.refresh(task)

    log_event(
        db,
        action="task.updated",
        entity_type="task",
        entity_id=task.id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={
            "actor_user_id": membership.user_id,
            "task_id": task.id,
            "changed_fields": changed_fields,
        },
    )

    if assignment_changed:
        log_event(
            db,
            action="task.assigned",
            entity_type="task",
            entity_id=task.id,
            organization_id=membership.organization_id,
            actor=membership.user.email,
            metadata={
                "actor_user_id": membership.user_id,
                "task_id": task.id,
                "assigned_to_user_id": task.assigned_to_user_id,
                "assigned_team_id": task.assigned_team_id,
            },
        )

    assignee_map = _assignee_user_map(db, [task])
    return _task_to_read(task, assignee_map)


@router.post("/tasks/{task_id}/complete", response_model=TaskRead)
def complete_task(
    task_id: str = Path(..., pattern=r"^[0-9a-fA-F-]{36}$"),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
) -> TaskRead:
    task = _get_org_task_or_404(db, organization_id=membership.organization_id, task_id=task_id)
    if not _can_write_task(db, membership=membership, task=task):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    task.status = "done"
    task.completed_at = _now_utc()
    db.add(task)
    db.commit()
    db.refresh(task)

    log_event(
        db,
        action="task.completed",
        entity_type="task",
        entity_id=task.id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={"actor_user_id": membership.user_id, "task_id": task.id},
    )

    assignee_map = _assignee_user_map(db, [task])
    return _task_to_read(task, assignee_map)


@router.post("/tasks/{task_id}/reopen", response_model=TaskRead)
def reopen_task(
    task_id: str = Path(..., pattern=r"^[0-9a-fA-F-]{36}$"),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
) -> TaskRead:
    task = _get_org_task_or_404(db, organization_id=membership.organization_id, task_id=task_id)
    if not _can_write_task(db, membership=membership, task=task):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    task.status = "open"
    task.completed_at = None
    db.add(task)
    db.commit()
    db.refresh(task)

    log_event(
        db,
        action="task.updated",
        entity_type="task",
        entity_id=task.id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={
            "actor_user_id": membership.user_id,
            "task_id": task.id,
            "changed_fields": {"status": "open", "completed_at": None},
        },
    )

    assignee_map = _assignee_user_map(db, [task])
    return _task_to_read(task, assignee_map)


@router.post("/tasks/bulk", response_model=TaskBulkResponse)
def bulk_update_tasks(
    payload: TaskBulkRequest,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
) -> TaskBulkResponse:
    task_ids = sorted({item.strip() for item in payload.task_ids if item.strip()})
    rows = db.execute(
        select(Task).where(
            Task.organization_id == membership.organization_id,
            Task.id.in_(task_ids),
        )
    ).scalars().all()
    if len(rows) != len(task_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more tasks not found")

    has_assign = _has_task_permission(db, membership=membership, permission="tasks:assign")
    updated_ids: list[str] = []
    assign_events: list[dict[str, str | None]] = []
    now = _now_utc()

    for task in rows:
        if not _can_write_task(db, membership=membership, task=task):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

        if payload.action == "complete":
            task.status = "done"
            task.completed_at = now
        elif payload.action == "assign":
            assignee_id = _validate_assignee_membership(
                db,
                organization_id=membership.organization_id,
                user_id=payload.assigned_to_user_id,
            )
            team_id = _assignee_team_key(
                db,
                organization_id=membership.organization_id,
                assigned_to_user_id=assignee_id,
                assigned_team_id=payload.assigned_team_id,
            )
            if not has_assign:
                if assignee_id is not None and assignee_id != membership.user_id:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Assignment requires tasks:assign")
                if team_id is not None and team_id != team_key_for_role(membership.role):
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Assignment requires tasks:assign")
            task.assigned_to_user_id = assignee_id
            task.assigned_team_id = team_id
            assign_events.append(
                {
                    "task_id": task.id,
                    "assigned_to_user_id": assignee_id,
                    "assigned_team_id": team_id,
                }
            )
        elif payload.action == "due_date":
            task.due_at = payload.due_at
        updated_ids.append(task.id)
        db.add(task)

    db.commit()

    log_event(
        db,
        action="task.bulk_updated",
        entity_type="task",
        entity_id=membership.organization_id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={
            "actor_user_id": membership.user_id,
            "task_ids": updated_ids,
            "action": payload.action,
            "assigned_to_user_id": payload.assigned_to_user_id,
            "assigned_team_id": payload.assigned_team_id,
            "due_at": payload.due_at.isoformat() if payload.due_at else None,
        },
    )

    for event in assign_events:
        log_event(
            db,
            action="task.assigned",
            entity_type="task",
            entity_id=str(event["task_id"]),
            organization_id=membership.organization_id,
            actor=membership.user.email,
            metadata={"actor_user_id": membership.user_id, **event},
        )

    return TaskBulkResponse(
        updated_task_ids=updated_ids,
        action=payload.action,
        updated_count=len(updated_ids),
    )


@router.get("/tasks/calendar", response_model=TaskCalendarResponse)
def tasks_calendar(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    scope: str = Query(default="self"),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
) -> TaskCalendarResponse:
    _validate_scope(db, membership=membership, scope=scope)

    now = _now_utc()
    start_value = start or _normalize_start_of_day(now)
    end_value = end or (start_value + timedelta(days=31))
    if end_value <= start_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end must be greater than start")

    filters = [
        Task.organization_id == membership.organization_id,
        Task.status.in_(("open", "in_progress")),
        Task.due_at.is_not(None),
        Task.due_at >= start_value,
        Task.due_at < end_value,
    ]
    filters.extend(_scope_predicates(db, membership=membership, scope=scope))

    rows = db.execute(
        select(Task).where(*filters).order_by(Task.due_at.asc(), Task.created_at.asc())
    ).scalars().all()
    assignee_map = _assignee_user_map(db, rows)

    grouped: dict[str, list[TaskCalendarItemRead]] = defaultdict(list)
    for row in rows:
        due_at = row.due_at
        if due_at is None:
            continue
        aware_due = due_at if due_at.tzinfo else due_at.replace(tzinfo=timezone.utc)
        day_key = aware_due.date().isoformat()
        grouped[day_key].append(
            TaskCalendarItemRead(
                id=row.id,
                title=row.title,
                due_at=aware_due,
                status=row.status,
                priority=row.priority,
                assigned_to_user_id=row.assigned_to_user_id,
                assigned_to_user_name=assignee_map.get(row.assigned_to_user_id or ""),
            )
        )

    day_rows = [
        TaskCalendarDayRead(day=day, count=len(items), items=items)
        for day, items in sorted(grouped.items(), key=lambda item: item[0])
    ]
    return TaskCalendarResponse(start=start_value, end=end_value, days=day_rows)


@router.get("/tasks/matrix", response_model=TaskMatrixResponse)
def tasks_matrix(
    scope: str = Query(default="team"),
    group_by: str = Query(default="team"),
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
) -> TaskMatrixResponse:
    scope_value = scope.strip().lower()
    if scope_value not in {"team", "all"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scope")
    if scope_value == "all":
        _validate_scope(db, membership=membership, scope="all")
    else:
        _validate_scope(db, membership=membership, scope="team")

    group_by_value = group_by.strip().lower()
    if group_by_value not in {"team", "user"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid group_by")

    filters = [
        Task.organization_id == membership.organization_id,
        Task.status.in_(("open", "in_progress")),
    ]
    filters.extend(_scope_predicates(db, membership=membership, scope=scope_value))

    rows = db.execute(
        select(Task).where(*filters).order_by(Task.created_at.desc())
    ).scalars().all()

    assignee_map = _assignee_user_map(db, rows)
    now = _now_utc()

    matrix: dict[str, dict[str, set[str] | int | str]] = {}
    for row in rows:
        bucket = _due_bucket(due_at=row.due_at, now=now)
        if group_by_value == "user":
            group_key = row.assigned_to_user_id or TEAM_UNASSIGNED
            if row.assigned_to_user_id:
                group_label = assignee_map.get(row.assigned_to_user_id, row.assigned_to_user_id)
            else:
                group_label = "Unassigned"
        else:
            group_key = row.assigned_team_id or TEAM_UNASSIGNED
            group_label = team_label(group_key)

        if group_key not in matrix:
            matrix[group_key] = {
                "group_label": group_label,
                **{
                    f"{name}_count": 0
                    for name in TASK_MATRIX_BUCKETS
                },
                **{
                    f"{name}_samples": set()
                    for name in TASK_MATRIX_BUCKETS
                },
            }

        matrix[group_key][f"{bucket}_count"] = int(matrix[group_key][f"{bucket}_count"]) + 1
        samples = matrix[group_key][f"{bucket}_samples"]
        if isinstance(samples, set) and len(samples) < 5:
            samples.add(row.id)

    response_rows: list[TaskMatrixRowRead] = []
    for group_key, payload in sorted(matrix.items(), key=lambda item: str(item[1]["group_label"])):
        buckets: dict[str, TaskMatrixBucketRead] = {}
        for bucket in TASK_MATRIX_BUCKETS:
            sample_ids = payload[f"{bucket}_samples"]
            buckets[bucket] = TaskMatrixBucketRead(
                count=int(payload[f"{bucket}_count"]),
                sample_task_ids=sorted(sample_ids) if isinstance(sample_ids, set) else [],
            )
        response_rows.append(
            TaskMatrixRowRead(
                group_key=group_key,
                group_label=str(payload["group_label"]),
                buckets=buckets,
            )
        )

    return TaskMatrixResponse(scope=scope_value, group_by=group_by_value, rows=response_rows)
