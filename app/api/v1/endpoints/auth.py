import hashlib
import json
import logging
import os
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, require_permission
from app.core.rbac import (
    ROLE_ADMIN,
    ROLE_CASE_MANAGER,
    normalize_role_key,
    permission_catalog,
    role_label,
)
from app.core.time import utc_now
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models.audit_event import AuditEvent
from app.db.models.encounter import Encounter
from app.db.models.form_submission import FormSubmission
from app.db.models.form_template import FormTemplate
from app.db.models.invite import Invite
from app.db.models.organization import Organization
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.password_reset_token import PasswordResetToken
from app.db.models.patient import Patient
from app.db.models.user import User
from app.db.session import get_db
from app.services.audit import log_event
from app.services.email import EmailDeliveryError, send_email
from app.services.rbac_roles import (
    ensure_org_roles_seeded,
    list_org_roles,
    normalize_role_for_org,
    update_role_permissions,
)


router = APIRouter(tags=["Auth"])
logger = logging.getLogger(__name__)

INVITE_EXPIRY_HOURS = 72
PASSWORD_RESET_EXPIRY_MINUTES = 60
DEFAULT_INVITE_ROLE = ROLE_CASE_MANAGER


class LoginRequest(BaseModel):
    email: str
    password: str
    organization_id: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    organization_id: str
    user_id: str


class BootstrapRequest(BaseModel):
    organization_name: str
    admin_email: str
    admin_password: str
    admin_name: str | None = None


class UserCreate(BaseModel):
    email: str
    full_name: str | None = None
    password: str
    role: str


class UserRead(BaseModel):
    id: str
    email: str
    full_name: str | None = None
    role: str
    is_active: bool


class MeResponse(BaseModel):
    id: str
    email: str
    full_name: str | None = None
    role: str
    organization_id: str


class InviteCreate(BaseModel):
    email: str
    allowed_roles: list[str] | None = None


class InviteRead(BaseModel):
    id: str
    email: str
    allowed_roles: list[str]
    status: str
    expires_at: str
    accepted_at: str | None = None


class AcceptInviteRequest(BaseModel):
    token: str
    role: str | None = None
    full_name: str | None = None
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class RequestPasswordResetRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class UserRoleUpdate(BaseModel):
    role: str


class RolePermissionRead(BaseModel):
    key: str
    name: str
    is_system: bool
    permissions: list[str]


class RolePermissionUpdate(BaseModel):
    permissions: list[str]


class InvitePreviewRead(BaseModel):
    email: str
    allowed_roles: list[str]
    expires_at: str
    status: str


class MessageResponse(BaseModel):
    message: str



def _normalize_email(raw: str) -> str:
    return raw.strip().lower()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _issue_raw_token() -> str:
    return secrets.token_urlsafe(40)


def _build_invite_link(token: str) -> str:
    base = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")
    return f"{base}/accept-invite?token={token}"


def _build_reset_link(token: str) -> str:
    base = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")
    return f"{base}/reset-password?token={token}"


def _is_expired(expires_at) -> bool:
    now = utc_now()
    if getattr(expires_at, "tzinfo", None) is None:
        return expires_at < now.replace(tzinfo=None)
    return expires_at < now


def _allowed_invite_roles(
    payload_roles: list[str] | None,
    *,
    db: Session,
    organization_id: str,
) -> list[str]:
    ensure_org_roles_seeded(db, organization_id=organization_id)
    available_roles = {row.key for row in list_org_roles(db, organization_id=organization_id)}
    roles = payload_roles or [DEFAULT_INVITE_ROLE]
    normalized: list[str] = []
    for role in roles:
        role_name = normalize_role_key(role)
        if role_name in normalized:
            continue
        if role_name not in available_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Invite roles must be valid organization roles: "
                    f"{', '.join(sorted(available_roles))}"
                ),
            )
        normalized.append(role_name)
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="allowed_roles cannot be empty",
        )
    return normalized


def _roles_to_json(roles: list[str]) -> str:
    return json.dumps(roles)


def _roles_from_json(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if isinstance(item, str)]


def _to_invite_read(row: Invite) -> InviteRead:
    return InviteRead(
        id=row.id,
        email=row.email,
        allowed_roles=_roles_from_json(row.allowed_roles_json),
        status=row.status,
        expires_at=row.expires_at.isoformat(),
        accepted_at=row.accepted_at.isoformat() if row.accepted_at else None,
    )


def _send_invite_email(*, to_email: str, invite_link: str) -> bool:
    body_text = (
        "You've been invited to join BEHR.\n\n"
        "Click the link below to accept your invite and set your password:\n\n"
        f"{invite_link}\n\n"
        "If you did not expect this invite, you may ignore this email."
    )
    body_html = (
        "<p>You've been invited to join BEHR.</p>"
        "<p>Click the link below to accept your invite and set your password:</p>"
        f"<p><a href=\"{invite_link}\">{invite_link}</a></p>"
        "<p>If you did not expect this invite, you may ignore this email.</p>"
    )
    return send_email(
        to=to_email,
        subject="You've been invited to BEHR",
        body_html=body_html,
        body_text=body_text,
    )


def _send_password_reset_email(*, to_email: str, reset_link: str) -> None:
    body_text = (
        "We received a request to reset your password.\n\n"
        f"Reset link: {reset_link}\n\n"
        "If you did not request this, you can ignore this email."
    )
    body_html = (
        "<p>We received a request to reset your password.</p>"
        f"<p>Reset link: <a href=\"{reset_link}\">{reset_link}</a></p>"
        "<p>If you did not request this, you can ignore this email.</p>"
    )
    try:
        send_email(
            to=to_email,
            subject="VEHR password reset",
            body_html=body_html,
            body_text=body_text,
        )
    except EmailDeliveryError as exc:
        logger.error(
            "Password reset email delivery failed for email=%s error=%s",
            to_email,
            str(exc),
        )


def _attempt_invite_email_delivery(
    *,
    db: Session,
    invite: Invite,
    actor_email: str,
    invite_link: str,
    context: str,
) -> None:
    log_event(
        db,
        action="invite.email_attempted",
        entity_type="invite",
        entity_id=invite.id,
        organization_id=invite.organization_id,
        actor=actor_email,
        metadata={"email": invite.email, "context": context},
    )

    try:
        sent = _send_invite_email(
            to_email=invite.email,
            invite_link=invite_link,
        )
        if sent:
            return

        logger.warning(
            "Invite email not sent because SMTP configuration is incomplete invite_id=%s email=%s context=%s",
            invite.id,
            invite.email,
            context,
        )
        log_event(
            db,
            action="invite.email_failed",
            entity_type="invite",
            entity_id=invite.id,
            organization_id=invite.organization_id,
            actor=actor_email,
            metadata={
                "email": invite.email,
                "context": context,
                "reason": "smtp_not_configured",
            },
        )
    except EmailDeliveryError as exc:
        logger.error(
            "Invite email delivery failed invite_id=%s email=%s context=%s error=%s",
            invite.id,
            invite.email,
            context,
            str(exc),
        )
        log_event(
            db,
            action="invite.email_failed",
            entity_type="invite",
            entity_id=invite.id,
            organization_id=invite.organization_id,
            actor=actor_email,
            metadata={
                "email": invite.email,
                "context": context,
                "reason": "smtp_error",
                "error": str(exc),
            },
        )
    except Exception as exc:
        logger.exception(
            "Unexpected invite email error invite_id=%s email=%s context=%s error=%s",
            invite.id,
            invite.email,
            context,
            str(exc),
        )
        log_event(
            db,
            action="invite.email_failed",
            entity_type="invite",
            entity_id=invite.id,
            organization_id=invite.organization_id,
            actor=actor_email,
            metadata={
                "email": invite.email,
                "context": context,
                "reason": "unexpected_error",
                "error": str(exc),
            },
        )


@router.post("/auth/bootstrap", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def bootstrap(request: BootstrapRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing_users = db.execute(select(func.count(User.id))).scalar_one()
    existing_orgs = db.execute(select(func.count(Organization.id))).scalar_one()
    if existing_users > 0 or existing_orgs > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bootstrap is disabled once data exists",
        )

    org = Organization(name=request.organization_name)
    db.add(org)
    db.commit()
    db.refresh(org)

    admin_email = _normalize_email(request.admin_email)
    user = User(
        email=admin_email,
        full_name=request.admin_name,
        hashed_password=hash_password(request.admin_password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    membership = OrganizationMembership(
        organization_id=org.id,
        user_id=user.id,
        role=ROLE_ADMIN,
    )
    db.add(membership)
    db.commit()
    ensure_org_roles_seeded(db, organization_id=org.id)

    for model in (Patient, Encounter, FormTemplate, FormSubmission, AuditEvent):
        db.execute(
            update(model)
            .where(model.organization_id.is_(None))
            .values(organization_id=org.id)
        )
    db.commit()

    log_event(
        db,
        action="bootstrap",
        entity_type="organization",
        entity_id=org.id,
        organization_id=org.id,
        actor=user.email,
    )

    token = create_access_token(
        {"sub": user.id, "org_id": org.id},
        expires_delta=timedelta(minutes=60),
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=60 * 60,
        organization_id=org.id,
        user_id=user.id,
    )


@router.post("/auth/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = _normalize_email(request.email)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )

    memberships = db.execute(
        select(OrganizationMembership).where(OrganizationMembership.user_id == user.id)
    ).scalars().all()
    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no organization membership",
        )

    organization_id = request.organization_id
    if organization_id:
        membership = next(
            (m for m in memberships if m.organization_id == organization_id),
            None,
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organization access denied",
            )
    else:
        if len(memberships) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="organization_id required for multi-organization users",
            )
        membership = memberships[0]
        organization_id = membership.organization_id

    token = create_access_token({"sub": user.id, "org_id": organization_id})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=60 * 60,
        organization_id=organization_id,
        user_id=user.id,
    )


@router.get("/auth/me", response_model=MeResponse)
def me(
    membership: OrganizationMembership = Depends(get_current_membership),
) -> MeResponse:
    return MeResponse(
        id=membership.user.id,
        email=membership.user.email,
        full_name=membership.user.full_name,
        role=normalize_role_key(membership.role),
        organization_id=membership.organization_id,
    )


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    request: UserCreate,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("users:manage")),
) -> UserRead:
    try:
        role_value = normalize_role_for_org(
            db,
            organization_id=membership.organization_id,
            role=request.role,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role",
        )

    email = _normalize_email(request.email)
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists",
        )

    user = User(
        email=email,
        full_name=request.full_name,
        hashed_password=hash_password(request.password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    membership_record = OrganizationMembership(
        organization_id=membership.organization_id,
        user_id=user.id,
        role=role_value,
    )
    db.add(membership_record)
    db.commit()

    log_event(
        db,
        action="create_user",
        entity_type="user",
        entity_id=user.id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={"role": membership_record.role, "role_label": role_label(membership_record.role)},
    )

    return UserRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=membership_record.role,
        is_active=user.is_active,
    )


@router.get("/users", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("users:manage")),
) -> list[UserRead]:
    ensure_org_roles_seeded(db, organization_id=membership.organization_id)
    records = (
        db.execute(
            select(OrganizationMembership, User).where(
                OrganizationMembership.organization_id == membership.organization_id,
                OrganizationMembership.user_id == User.id,
            )
        )
        .all()
    )
    return [
        UserRead(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=normalize_role_key(membership_record.role),
            is_active=user.is_active,
        )
        for membership_record, user in records
    ]


@router.patch("/admin/users/{user_id}/role", response_model=UserRead)
def update_user_role(
    user_id: str,
    request: UserRoleUpdate,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("users:manage")),
) -> UserRead:
    try:
        role_value = normalize_role_for_org(
            db,
            organization_id=membership.organization_id,
            role=request.role,
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")

    membership_record = db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == membership.organization_id,
            OrganizationMembership.user_id == user_id,
        )
    ).scalar_one_or_none()
    if not membership_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User membership not found")

    membership_record.role = role_value
    db.add(membership_record)
    db.commit()
    db.refresh(membership_record)

    log_event(
        db,
        action="user.role_updated",
        entity_type="user",
        entity_id=user_id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={"role": role_value, "role_label": role_label(role_value)},
    )

    user = db.get(User, user_id)
    return UserRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=normalize_role_key(membership_record.role),
        is_active=user.is_active,
    )


@router.get("/admin/permissions/catalog", response_model=list[str])
def get_permission_catalog(
    _: None = Depends(require_permission("admin:role_permissions")),
) -> list[str]:
    return permission_catalog()


@router.get("/admin/roles", response_model=list[RolePermissionRead])
def list_role_permissions(
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("admin:role_permissions")),
) -> list[RolePermissionRead]:
    roles = list_org_roles(db, organization_id=membership.organization_id)
    return [
        RolePermissionRead(
            key=row.key,
            name=row.name,
            is_system=row.is_system,
            permissions=list(row.permissions),
        )
        for row in roles
    ]


@router.put("/admin/roles/{role_key}/permissions", response_model=RolePermissionRead)
def replace_role_permissions(
    role_key: str,
    payload: RolePermissionUpdate,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("admin:role_permissions")),
) -> RolePermissionRead:
    try:
        updated = update_role_permissions(
            db,
            organization_id=membership.organization_id,
            role_key=role_key,
            permissions=payload.permissions,
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    log_event(
        db,
        action="role.permissions_updated",
        entity_type="role",
        entity_id=updated.key,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={"permissions": list(updated.permissions)},
    )

    return RolePermissionRead(
        key=updated.key,
        name=updated.name,
        is_system=updated.is_system,
        permissions=list(updated.permissions),
    )


@router.get("/admin/invites", response_model=list[InviteRead])
def list_invites(
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("users:manage")),
) -> list[InviteRead]:
    rows = db.execute(
        select(Invite)
        .where(Invite.organization_id == membership.organization_id)
        .order_by(Invite.created_at.desc())
    ).scalars().all()
    return [_to_invite_read(row) for row in rows]


@router.post("/admin/invites", response_model=InviteRead, status_code=status.HTTP_201_CREATED)
def create_invite(
    request: InviteCreate,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("users:manage")),
) -> InviteRead:
    email = _normalize_email(request.email)
    allowed_roles = _allowed_invite_roles(
        request.allowed_roles,
        db=db,
        organization_id=membership.organization_id,
    )

    raw_token = _issue_raw_token()
    token_hash = _hash_token(raw_token)
    row = Invite(
        organization_id=membership.organization_id,
        email=email,
        allowed_roles_json=_roles_to_json(allowed_roles),
        token_hash=token_hash,
        status="pending",
        expires_at=utc_now() + timedelta(hours=INVITE_EXPIRY_HOURS),
        invited_by_user_id=membership.user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    _attempt_invite_email_delivery(
        db=db,
        invite=row,
        actor_email=membership.user.email,
        invite_link=_build_invite_link(raw_token),
        context="create",
    )

    log_event(
        db,
        action="invite.created",
        entity_type="invite",
        entity_id=row.id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
        metadata={"email": email, "allowed_roles": allowed_roles},
    )
    return _to_invite_read(row)


@router.post("/admin/invites/{invite_id}/resend", response_model=InviteRead)
def resend_invite(
    invite_id: str,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("users:manage")),
) -> InviteRead:
    row = db.execute(
        select(Invite).where(
            Invite.id == invite_id,
            Invite.organization_id == membership.organization_id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if row.status == "accepted":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite already accepted")
    if row.status == "revoked":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite is revoked")

    raw_token = _issue_raw_token()
    row.token_hash = _hash_token(raw_token)
    row.status = "pending"
    row.expires_at = utc_now() + timedelta(hours=INVITE_EXPIRY_HOURS)
    row.updated_at = utc_now()
    db.add(row)
    db.commit()
    db.refresh(row)

    _attempt_invite_email_delivery(
        db=db,
        invite=row,
        actor_email=membership.user.email,
        invite_link=_build_invite_link(raw_token),
        context="resend",
    )

    log_event(
        db,
        action="invite.resent",
        entity_type="invite",
        entity_id=row.id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
    )
    return _to_invite_read(row)


@router.post("/admin/invites/{invite_id}/revoke", response_model=InviteRead)
def revoke_invite(
    invite_id: str,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
    _: None = Depends(require_permission("users:manage")),
) -> InviteRead:
    row = db.execute(
        select(Invite).where(
            Invite.id == invite_id,
            Invite.organization_id == membership.organization_id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if row.status == "accepted":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite already accepted")

    row.status = "revoked"
    row.updated_at = utc_now()
    db.add(row)
    db.commit()
    db.refresh(row)

    log_event(
        db,
        action="invite.revoked",
        entity_type="invite",
        entity_id=row.id,
        organization_id=membership.organization_id,
        actor=membership.user.email,
    )
    return _to_invite_read(row)


@router.get("/auth/invites/preview", response_model=InvitePreviewRead)
def preview_invite(
    token: str,
    db: Session = Depends(get_db),
) -> InvitePreviewRead:
    token_hash = _hash_token(token)
    invite = db.execute(
        select(Invite).where(
            Invite.token_hash == token_hash,
            Invite.status == "pending",
        )
    ).scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if _is_expired(invite.expires_at):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite token expired")

    allowed_roles = _roles_from_json(invite.allowed_roles_json)
    if not allowed_roles:
        allowed_roles = [DEFAULT_INVITE_ROLE]

    return InvitePreviewRead(
        email=invite.email,
        allowed_roles=[normalize_role_key(item) for item in allowed_roles],
        expires_at=invite.expires_at.isoformat(),
        status=invite.status,
    )


@router.post("/auth/accept-invite", response_model=TokenResponse)
def accept_invite(request: AcceptInviteRequest, db: Session = Depends(get_db)) -> TokenResponse:
    token_hash = _hash_token(request.token)
    invite = db.execute(
        select(Invite).where(
            Invite.token_hash == token_hash,
            Invite.status == "pending",
        )
    ).scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invite token")
    if _is_expired(invite.expires_at):
        invite.status = "expired"
        invite.updated_at = utc_now()
        db.add(invite)
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite token expired")

    ensure_org_roles_seeded(db, organization_id=invite.organization_id)
    allowed_roles = _roles_from_json(invite.allowed_roles_json)
    if not allowed_roles:
        allowed_roles = [DEFAULT_INVITE_ROLE]

    if request.role and request.role.strip():
        try:
            role = normalize_role_for_org(
                db,
                organization_id=invite.organization_id,
                role=request.role,
            )
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    elif len(allowed_roles) == 1:
        role = normalize_role_key(allowed_roles[0])
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role selection is required for this invite",
        )

    if role not in {normalize_role_key(item) for item in allowed_roles}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected role is not allowed for this invite",
        )

    user = db.execute(select(User).where(User.email == invite.email)).scalar_one_or_none()
    if user is None:
        user = User(
            email=invite.email,
            full_name=request.full_name,
            hashed_password=hash_password(request.password),
            is_active=True,
        )
        db.add(user)
        db.flush()
    else:
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")
        if request.full_name is not None:
            user.full_name = request.full_name
        user.hashed_password = hash_password(request.password)
        db.add(user)

    existing_membership = db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == invite.organization_id,
            OrganizationMembership.user_id == user.id,
        )
    ).scalar_one_or_none()
    if existing_membership:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already belongs to this organization",
        )

    db.add(
        OrganizationMembership(
            organization_id=invite.organization_id,
            user_id=user.id,
            role=role,
        )
    )

    invite.status = "accepted"
    invite.accepted_at = utc_now()
    invite.updated_at = utc_now()
    db.add(invite)
    db.commit()
    db.refresh(user)

    log_event(
        db,
        action="invite.accepted",
        entity_type="invite",
        entity_id=invite.id,
        organization_id=invite.organization_id,
        actor=user.email,
        metadata={"role": role, "role_label": role_label(role)},
    )

    token = create_access_token({"sub": user.id, "org_id": invite.organization_id})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=60 * 60,
        organization_id=invite.organization_id,
        user_id=user.id,
    )


@router.post("/auth/change-password", response_model=MessageResponse)
def change_password(
    request: ChangePasswordRequest,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(get_current_membership),
) -> MessageResponse:
    user = membership.user
    if not verify_password(request.current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid current password")

    user.hashed_password = hash_password(request.new_password)
    db.add(user)
    db.commit()

    log_event(
        db,
        action="password.changed",
        entity_type="user",
        entity_id=user.id,
        organization_id=membership.organization_id,
        actor=user.email,
    )
    return MessageResponse(message="Password updated")


@router.post("/auth/request-password-reset", response_model=MessageResponse)
def request_password_reset(
    request: RequestPasswordResetRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    email = _normalize_email(request.email)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user and user.is_active:
        raw_token = _issue_raw_token()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=_hash_token(raw_token),
                expires_at=utc_now() + timedelta(minutes=PASSWORD_RESET_EXPIRY_MINUTES),
            )
        )
        db.commit()
        _send_password_reset_email(
            to_email=user.email,
            reset_link=_build_reset_link(raw_token),
        )

    return MessageResponse(message="If the account exists, a reset link has been sent")


@router.post("/auth/reset-password", response_model=MessageResponse)
def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    token_hash = _hash_token(request.token)
    row = db.execute(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token")
    if _is_expired(row.expires_at):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset token expired")

    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token")

    user.hashed_password = hash_password(request.new_password)
    row.used_at = utc_now()
    db.add(user)
    db.add(row)
    db.commit()

    log_event(
        db,
        action="password.reset",
        entity_type="user",
        entity_id=user.id,
        actor=user.email,
    )
    return MessageResponse(message="Password reset successful")
