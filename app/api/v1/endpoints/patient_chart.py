from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_membership, get_current_organization, require_permission
from app.core.time import utc_now
from app.db.models.episode_of_care import EpisodeOfCare
from app.db.models.organization_membership import OrganizationMembership
from app.db.models.patient import Patient
from app.db.models.patient_note import PatientNote
from app.db.models.patient_care_team import PatientCareTeam
from app.db.models.patient_requirement import PatientRequirement
from app.db.models.patient_treatment_stage import PatientTreatmentStage
from app.db.models.patient_treatment_stage_event import PatientTreatmentStageEvent
from app.db.models.user import User
from app.db.session import get_db
from app.services.audit import log_event


router = APIRouter(tags=["Patient Chart"])

SERVICE_CATEGORIES = {"intake", "sud", "mh", "psych", "cm"}
EPISODE_STATUSES = {"active", "discharged"}
CARE_TEAM_ROLES = {
    "counselor",
    "psych_provider",
    "case_manager",
    "supervisor",
    "primary_coordinator",
}
REQUIREMENT_TYPES = {
    "missing_demographics",
    "missing_insurance",
    "missing_consent",
    "missing_assessment",
    "unsigned_note",
    "expiring_roi",
}
REQUIREMENT_STATUSES = {"open", "resolved"}
TREATMENT_STAGES = {
    "intake_started",
    "paperwork_completed",
    "assessment_completed",
    "enrolled",
    "active_treatment",
    "step_down_transition",
    "discharge_planning",
    "discharged",
}


class EpisodeCreate(BaseModel):
    admit_date: date
    referral_source: str | None = Field(default=None, max_length=200)
    reason_for_admission: str | None = None
    primary_service_category: str
    court_involved: bool = False
    status: str = "active"
    discharge_date: date | None = None
    discharge_disposition: str | None = Field(default=None, max_length=200)


class EpisodeUpdate(BaseModel):
    admit_date: date | None = None
    referral_source: str | None = Field(default=None, max_length=200)
    reason_for_admission: str | None = None
    primary_service_category: str | None = None
    court_involved: bool | None = None
    status: str | None = None
    discharge_date: date | None = None
    discharge_disposition: str | None = Field(default=None, max_length=200)


class EpisodeRead(BaseModel):
    id: str
    patient_id: str
    admit_date: date
    discharge_date: date | None = None
    referral_source: str | None = None
    reason_for_admission: str | None = None
    primary_service_category: str
    court_involved: bool
    discharge_disposition: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CareTeamCreate(BaseModel):
    episode_id: str | None = None
    role: str
    user_id: str


class CareTeamRead(BaseModel):
    id: str
    patient_id: str
    episode_id: str
    role: str
    user_id: str
    assigned_at: datetime
    user_email: str
    user_full_name: str | None = None


class RequirementCreate(BaseModel):
    episode_id: str | None = None
    requirement_type: str
    auto_generated: bool = False


class RequirementUpdate(BaseModel):
    status: str


class RequirementRead(BaseModel):
    id: str
    patient_id: str
    episode_id: str
    requirement_type: str
    status: str
    resolved_at: datetime | None = None
    auto_generated: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TreatmentStageUpdate(BaseModel):
    episode_id: str | None = None
    stage: str
    reason: str | None = None


class TreatmentStageRead(BaseModel):
    id: str | None = None
    episode_id: str | None = None
    stage: str | None = None
    updated_by_user_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TreatmentStageEventRead(BaseModel):
    id: str
    episode_id: str
    from_stage: str | None = None
    to_stage: str
    reason: str | None = None
    changed_by_user_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


def _normalize_choice(value: str, *, label: str, allowed: set[str]) -> str:
    normalized = value.strip().lower()
    if normalized not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {label}. Expected one of: {', '.join(sorted(allowed))}",
        )
    return normalized


def _get_patient_or_404(db: Session, *, patient_id: str, organization_id: str) -> Patient:
    patient = db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return patient


def _get_episode_or_404(db: Session, *, episode_id: str, organization_id: str) -> EpisodeOfCare:
    episode = db.execute(
        select(EpisodeOfCare).where(
            EpisodeOfCare.id == episode_id,
            EpisodeOfCare.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    return episode


def _get_active_episode(
    db: Session,
    *,
    patient_id: str,
    organization_id: str,
) -> EpisodeOfCare | None:
    return db.execute(
        select(EpisodeOfCare).where(
            EpisodeOfCare.organization_id == organization_id,
            EpisodeOfCare.patient_id == patient_id,
            EpisodeOfCare.status == "active",
        )
    ).scalar_one_or_none()


def _validate_episode_window(
    *,
    admit_date: date,
    discharge_date: date | None,
    status_value: str,
) -> None:
    if discharge_date is not None and discharge_date < admit_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="discharge_date cannot be before admit_date",
        )
    if status_value == "active" and discharge_date is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active episodes cannot include discharge_date",
        )
    if status_value == "discharged" and discharge_date is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Discharged episodes require discharge_date",
        )


def _enforce_single_active_episode(
    db: Session,
    *,
    patient_id: str,
    organization_id: str,
    exclude_episode_id: str | None = None,
) -> None:
    query = select(EpisodeOfCare).where(
        EpisodeOfCare.organization_id == organization_id,
        EpisodeOfCare.patient_id == patient_id,
        EpisodeOfCare.status == "active",
    )
    if exclude_episode_id:
        query = query.where(EpisodeOfCare.id != exclude_episode_id)
    existing = db.execute(query).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Patient already has an active episode",
        )


def _get_valid_team_user(
    db: Session,
    *,
    user_id: str,
    organization_id: str,
) -> User:
    membership = db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
    ).scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assigned user is not a member of this organization",
        )
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assigned user is inactive",
        )
    return user


def _sync_auto_requirement(
    db: Session,
    *,
    organization_id: str,
    patient_id: str,
    episode_id: str,
    requirement_type: str,
    should_exist: bool,
) -> list[PatientRequirement]:
    rows = db.execute(
        select(PatientRequirement).where(
            PatientRequirement.organization_id == organization_id,
            PatientRequirement.patient_id == patient_id,
            PatientRequirement.episode_id == episode_id,
            PatientRequirement.requirement_type == requirement_type,
        )
    ).scalars().all()

    open_row = next((row for row in rows if row.status == "open"), None)
    latest_resolved = next((row for row in rows if row.status == "resolved"), None)
    changed: list[PatientRequirement] = []

    if should_exist:
        if open_row is not None:
            return changed
        if latest_resolved is not None and latest_resolved.auto_generated:
            latest_resolved.status = "open"
            latest_resolved.resolved_at = None
            latest_resolved.updated_at = utc_now()
            db.add(latest_resolved)
            changed.append(latest_resolved)
            return changed
        created = PatientRequirement(
            organization_id=organization_id,
            patient_id=patient_id,
            episode_id=episode_id,
            requirement_type=requirement_type,
            status="open",
            auto_generated=True,
        )
        db.add(created)
        changed.append(created)
        return changed

    if open_row is not None and open_row.auto_generated:
        open_row.status = "resolved"
        open_row.resolved_at = utc_now()
        open_row.updated_at = utc_now()
        db.add(open_row)
        changed.append(open_row)
    return changed


def _record_stage_event(
    db: Session,
    *,
    stage_row: PatientTreatmentStage | None,
    organization_id: str,
    patient_id: str,
    episode_id: str,
    from_stage: str | None,
    to_stage: str,
    reason: str | None,
    changed_by_user_id: str | None,
) -> PatientTreatmentStageEvent:
    event = PatientTreatmentStageEvent(
        organization_id=organization_id,
        patient_id=patient_id,
        episode_id=episode_id,
        patient_treatment_stage_id=stage_row.id if stage_row else None,
        from_stage=from_stage,
        to_stage=to_stage,
        reason=reason,
        changed_by_user_id=changed_by_user_id,
    )
    db.add(event)
    return event


def _upsert_treatment_stage(
    db: Session,
    *,
    organization_id: str,
    patient_id: str,
    episode_id: str,
    to_stage: str,
    changed_by_user_id: str | None,
    reason: str | None,
) -> PatientTreatmentStage:
    row = db.execute(
        select(PatientTreatmentStage).where(
            PatientTreatmentStage.organization_id == organization_id,
            PatientTreatmentStage.patient_id == patient_id,
            PatientTreatmentStage.episode_id == episode_id,
        )
    ).scalar_one_or_none()
    if row is None:
        row = PatientTreatmentStage(
            organization_id=organization_id,
            patient_id=patient_id,
            episode_id=episode_id,
            stage=to_stage,
            updated_by_user_id=changed_by_user_id,
        )
        db.add(row)
        db.flush()
        _record_stage_event(
            db,
            stage_row=row,
            organization_id=organization_id,
            patient_id=patient_id,
            episode_id=episode_id,
            from_stage=None,
            to_stage=to_stage,
            reason=reason,
            changed_by_user_id=changed_by_user_id,
        )
        return row

    previous = row.stage
    if previous != to_stage:
        row.stage = to_stage
        row.updated_by_user_id = changed_by_user_id
        row.updated_at = utc_now()
        db.add(row)
        _record_stage_event(
            db,
            stage_row=row,
            organization_id=organization_id,
            patient_id=patient_id,
            episode_id=episode_id,
            from_stage=previous,
            to_stage=to_stage,
            reason=reason,
            changed_by_user_id=changed_by_user_id,
        )
    return row
@router.get("/patients/{patient_id}/episodes", response_model=list[EpisodeRead])
def list_patient_episodes(
    patient_id: str,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    _: None = Depends(require_permission("patients:read")),
) -> list[EpisodeRead]:
    _get_patient_or_404(db, patient_id=patient_id, organization_id=organization.id)
    rows = db.execute(
        select(EpisodeOfCare)
        .where(
            EpisodeOfCare.organization_id == organization.id,
            EpisodeOfCare.patient_id == patient_id,
        )
        .order_by(EpisodeOfCare.admit_date.desc(), EpisodeOfCare.created_at.desc())
    ).scalars().all()
    return rows


@router.post("/patients/{patient_id}/episodes", response_model=EpisodeRead, status_code=status.HTTP_201_CREATED)
def create_episode(
    patient_id: str,
    payload: EpisodeCreate,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("patients:write")),
) -> EpisodeRead:
    _get_patient_or_404(db, patient_id=patient_id, organization_id=organization.id)
    primary_service_category = _normalize_choice(
        payload.primary_service_category,
        label="primary_service_category",
        allowed=SERVICE_CATEGORIES,
    )
    status_value = _normalize_choice(payload.status, label="status", allowed=EPISODE_STATUSES)
    _validate_episode_window(
        admit_date=payload.admit_date,
        discharge_date=payload.discharge_date,
        status_value=status_value,
    )
    if status_value == "active":
        _enforce_single_active_episode(
            db,
            patient_id=patient_id,
            organization_id=organization.id,
        )

    row = EpisodeOfCare(
        organization_id=organization.id,
        patient_id=patient_id,
        admit_date=payload.admit_date,
        discharge_date=payload.discharge_date,
        referral_source=payload.referral_source.strip() if payload.referral_source else None,
        reason_for_admission=payload.reason_for_admission.strip() if payload.reason_for_admission else None,
        primary_service_category=primary_service_category,
        court_involved=payload.court_involved,
        discharge_disposition=(
            payload.discharge_disposition.strip() if payload.discharge_disposition else None
        ),
        status=status_value,
    )
    db.add(row)
    db.flush()
    if status_value == "active":
        _upsert_treatment_stage(
            db,
            organization_id=organization.id,
            patient_id=patient_id,
            episode_id=row.id,
            to_stage="intake_started",
            changed_by_user_id=membership.user_id,
            reason="Episode created",
        )
    db.commit()
    db.refresh(row)

    log_event(
        db,
        action="episode.created",
        entity_type="episode_of_care",
        entity_id=row.id,
        organization_id=organization.id,
        patient_id=patient_id,
        actor=membership.user.email,
        metadata={
            "status": row.status,
            "admit_date": row.admit_date.isoformat(),
            "discharge_date": row.discharge_date.isoformat() if row.discharge_date else None,
            "primary_service_category": row.primary_service_category,
        },
    )
    return row


@router.patch("/episodes/{episode_id}", response_model=EpisodeRead)
def update_episode(
    episode_id: str,
    payload: EpisodeUpdate,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("patients:write")),
) -> EpisodeRead:
    row = _get_episode_or_404(db, episode_id=episode_id, organization_id=organization.id)

    status_value = (
        _normalize_choice(payload.status, label="status", allowed=EPISODE_STATUSES)
        if payload.status is not None
        else row.status
    )
    admit_date = payload.admit_date if payload.admit_date is not None else row.admit_date
    discharge_date = payload.discharge_date if "discharge_date" in payload.model_fields_set else row.discharge_date
    primary_service_category = (
        _normalize_choice(
            payload.primary_service_category,
            label="primary_service_category",
            allowed=SERVICE_CATEGORIES,
        )
        if payload.primary_service_category is not None
        else row.primary_service_category
    )
    _validate_episode_window(
        admit_date=admit_date,
        discharge_date=discharge_date,
        status_value=status_value,
    )
    if status_value == "active":
        _enforce_single_active_episode(
            db,
            patient_id=row.patient_id,
            organization_id=organization.id,
            exclude_episode_id=row.id,
        )

    row.admit_date = admit_date
    row.discharge_date = discharge_date
    if payload.referral_source is not None:
        row.referral_source = payload.referral_source.strip() if payload.referral_source else None
    if payload.reason_for_admission is not None:
        row.reason_for_admission = (
            payload.reason_for_admission.strip() if payload.reason_for_admission else None
        )
    row.primary_service_category = primary_service_category
    if payload.court_involved is not None:
        row.court_involved = payload.court_involved
    if "discharge_disposition" in payload.model_fields_set:
        row.discharge_disposition = (
            payload.discharge_disposition.strip() if payload.discharge_disposition else None
        )
    row.status = status_value
    row.updated_at = utc_now()
    db.add(row)

    if status_value == "discharged":
        _upsert_treatment_stage(
            db,
            organization_id=organization.id,
            patient_id=row.patient_id,
            episode_id=row.id,
            to_stage="discharged",
            changed_by_user_id=membership.user_id,
            reason="Episode discharged",
        )

    db.commit()
    db.refresh(row)

    log_event(
        db,
        action="episode.updated",
        entity_type="episode_of_care",
        entity_id=row.id,
        organization_id=organization.id,
        patient_id=row.patient_id,
        actor=membership.user.email,
        metadata={
            "status": row.status,
            "admit_date": row.admit_date.isoformat(),
            "discharge_date": row.discharge_date.isoformat() if row.discharge_date else None,
            "primary_service_category": row.primary_service_category,
            "court_involved": row.court_involved,
        },
    )
    return row


@router.get("/patients/{patient_id}/care-team", response_model=list[CareTeamRead])
def list_patient_care_team(
    patient_id: str,
    episode_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    _: None = Depends(require_permission("patients:read")),
) -> list[CareTeamRead]:
    _get_patient_or_404(db, patient_id=patient_id, organization_id=organization.id)
    resolved_episode_id = episode_id
    if resolved_episode_id is None:
        active_episode = _get_active_episode(
            db,
            patient_id=patient_id,
            organization_id=organization.id,
        )
        if active_episode is None:
            return []
        resolved_episode_id = active_episode.id
    else:
        episode = _get_episode_or_404(db, episode_id=resolved_episode_id, organization_id=organization.id)
        if episode.patient_id != patient_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Episode not found for patient",
            )

    rows = db.execute(
        select(PatientCareTeam)
        .options(selectinload(PatientCareTeam.user))
        .where(
            PatientCareTeam.organization_id == organization.id,
            PatientCareTeam.patient_id == patient_id,
            PatientCareTeam.episode_id == resolved_episode_id,
        )
        .order_by(PatientCareTeam.assigned_at.asc())
    ).scalars().all()
    return [
        CareTeamRead(
            id=row.id,
            patient_id=row.patient_id,
            episode_id=row.episode_id,
            role=row.role,
            user_id=row.user_id,
            assigned_at=row.assigned_at,
            user_email=row.user.email,
            user_full_name=row.user.full_name,
        )
        for row in rows
    ]
@router.post("/patients/{patient_id}/care-team", response_model=CareTeamRead, status_code=status.HTTP_201_CREATED)
def assign_patient_care_team(
    patient_id: str,
    payload: CareTeamCreate,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("patients:write")),
) -> CareTeamRead:
    _get_patient_or_404(db, patient_id=patient_id, organization_id=organization.id)
    role_value = _normalize_choice(payload.role, label="care team role", allowed=CARE_TEAM_ROLES)

    if payload.episode_id:
        episode = _get_episode_or_404(db, episode_id=payload.episode_id, organization_id=organization.id)
    else:
        episode = _get_active_episode(
            db,
            patient_id=patient_id,
            organization_id=organization.id,
        )
        if episode is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active episode found; provide episode_id",
            )

    if episode.patient_id != patient_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found for patient",
        )

    user = _get_valid_team_user(
        db,
        user_id=payload.user_id,
        organization_id=organization.id,
    )

    duplicate = db.execute(
        select(PatientCareTeam).where(
            PatientCareTeam.organization_id == organization.id,
            PatientCareTeam.patient_id == patient_id,
            PatientCareTeam.episode_id == episode.id,
            PatientCareTeam.role == role_value,
            PatientCareTeam.user_id == user.id,
        )
    ).scalar_one_or_none()
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Care team assignment already exists",
        )

    row = PatientCareTeam(
        organization_id=organization.id,
        patient_id=patient_id,
        episode_id=episode.id,
        role=role_value,
        user_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    log_event(
        db,
        action="care_team.assigned",
        entity_type="patient_care_team",
        entity_id=row.id,
        organization_id=organization.id,
        patient_id=patient_id,
        actor=membership.user.email,
        metadata={
            "episode_id": row.episode_id,
            "role": row.role,
            "user_id": row.user_id,
        },
    )
    return CareTeamRead(
        id=row.id,
        patient_id=row.patient_id,
        episode_id=row.episode_id,
        role=row.role,
        user_id=row.user_id,
        assigned_at=row.assigned_at,
        user_email=user.email,
        user_full_name=user.full_name,
    )


@router.delete("/care-team/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_patient_care_team_assignment(
    assignment_id: str,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("patients:write")),
) -> None:
    row = db.execute(
        select(PatientCareTeam).where(
            PatientCareTeam.id == assignment_id,
            PatientCareTeam.organization_id == organization.id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Care team assignment not found")
    patient_id = row.patient_id
    db.delete(row)
    db.commit()

    log_event(
        db,
        action="care_team.removed",
        entity_type="patient_care_team",
        entity_id=assignment_id,
        organization_id=organization.id,
        patient_id=patient_id,
        actor=membership.user.email,
    )
    return None


@router.get("/patients/{patient_id}/requirements", response_model=list[RequirementRead])
def list_patient_requirements(
    patient_id: str,
    episode_id: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    _: None = Depends(require_permission("patients:read")),
) -> list[RequirementRead]:
    _get_patient_or_404(db, patient_id=patient_id, organization_id=organization.id)
    filters = [
        PatientRequirement.organization_id == organization.id,
        PatientRequirement.patient_id == patient_id,
    ]
    if episode_id is not None:
        episode = _get_episode_or_404(db, episode_id=episode_id, organization_id=organization.id)
        if episode.patient_id != patient_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Episode not found for patient",
            )
        filters.append(PatientRequirement.episode_id == episode.id)
    if status_value is not None:
        filters.append(
            PatientRequirement.status
            == _normalize_choice(status_value, label="requirement status", allowed=REQUIREMENT_STATUSES)
        )

    rows = db.execute(
        select(PatientRequirement)
        .where(*filters)
        .order_by(PatientRequirement.created_at.desc())
    ).scalars().all()
    return rows


@router.post("/patients/{patient_id}/requirements", response_model=RequirementRead, status_code=status.HTTP_201_CREATED)
def create_patient_requirement(
    patient_id: str,
    payload: RequirementCreate,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("patients:write")),
) -> RequirementRead:
    _get_patient_or_404(db, patient_id=patient_id, organization_id=organization.id)
    requirement_type = _normalize_choice(
        payload.requirement_type,
        label="requirement_type",
        allowed=REQUIREMENT_TYPES,
    )

    if payload.episode_id:
        episode = _get_episode_or_404(db, episode_id=payload.episode_id, organization_id=organization.id)
    else:
        episode = _get_active_episode(
            db,
            patient_id=patient_id,
            organization_id=organization.id,
        )
        if episode is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active episode found; provide episode_id",
            )
    if episode.patient_id != patient_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found for patient",
        )

    row = PatientRequirement(
        organization_id=organization.id,
        patient_id=patient_id,
        episode_id=episode.id,
        requirement_type=requirement_type,
        status="open",
        auto_generated=payload.auto_generated,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    log_event(
        db,
        action="requirement.created",
        entity_type="patient_requirement",
        entity_id=row.id,
        organization_id=organization.id,
        patient_id=patient_id,
        actor=membership.user.email,
        metadata={
            "episode_id": row.episode_id,
            "requirement_type": row.requirement_type,
            "auto_generated": row.auto_generated,
        },
    )
    return row
@router.post("/patients/{patient_id}/requirements/refresh", response_model=list[RequirementRead])
def refresh_patient_requirements(
    patient_id: str,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("patients:write")),
) -> list[RequirementRead]:
    patient = _get_patient_or_404(db, patient_id=patient_id, organization_id=organization.id)
    episode = _get_active_episode(
        db,
        patient_id=patient_id,
        organization_id=organization.id,
    )
    if episode is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active episode found",
        )

    # Keep this lightweight and safe: additional requirement generators can be
    # added incrementally without changing existing requirement records.
    missing_demographics = (
        patient.dob is None
        or not patient.first_name.strip()
        or not patient.last_name.strip()
        or (not patient.phone and not patient.email)
    )
    changed = _sync_auto_requirement(
        db,
        organization_id=organization.id,
        patient_id=patient_id,
        episode_id=episode.id,
        requirement_type="missing_demographics",
        should_exist=missing_demographics,
    )
    # Keep unsigned-note logic lightweight for now. We treat any draft note on
    # the patient as an open requirement and resolve it once all notes are signed.
    has_unsigned_notes = (
        db.execute(
            select(PatientNote.id)
            .where(
                PatientNote.organization_id == organization.id,
                PatientNote.patient_id == patient_id,
                PatientNote.status == "draft",
            )
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )
    changed.extend(
        _sync_auto_requirement(
            db,
            organization_id=organization.id,
            patient_id=patient_id,
            episode_id=episode.id,
            requirement_type="unsigned_note",
            should_exist=has_unsigned_notes,
        )
    )
    # TODO: add automatic generators for missing_insurance, missing_consent,
    # missing_assessment, and expiring_roi.

    db.commit()
    for row in changed:
        log_event(
            db,
            action="requirement.updated",
            entity_type="patient_requirement",
            entity_id=row.id,
            organization_id=organization.id,
            patient_id=patient_id,
            actor=membership.user.email,
            metadata={
                "episode_id": row.episode_id,
                "requirement_type": row.requirement_type,
                "status": row.status,
                "auto_generated": row.auto_generated,
            },
        )

    rows = db.execute(
        select(PatientRequirement).where(
            PatientRequirement.organization_id == organization.id,
            PatientRequirement.patient_id == patient_id,
            PatientRequirement.episode_id == episode.id,
        )
    ).scalars().all()
    return rows


@router.patch("/requirements/{requirement_id}", response_model=RequirementRead)
def update_patient_requirement(
    requirement_id: str,
    payload: RequirementUpdate,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("patients:write")),
) -> RequirementRead:
    row = db.execute(
        select(PatientRequirement).where(
            PatientRequirement.id == requirement_id,
            PatientRequirement.organization_id == organization.id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found")
    row.status = _normalize_choice(
        payload.status,
        label="requirement status",
        allowed=REQUIREMENT_STATUSES,
    )
    row.resolved_at = utc_now() if row.status == "resolved" else None
    row.updated_at = utc_now()
    db.add(row)
    db.commit()
    db.refresh(row)

    log_event(
        db,
        action="requirement.updated",
        entity_type="patient_requirement",
        entity_id=row.id,
        organization_id=organization.id,
        patient_id=row.patient_id,
        actor=membership.user.email,
        metadata={
            "episode_id": row.episode_id,
            "requirement_type": row.requirement_type,
            "status": row.status,
        },
    )
    return row


@router.get("/patients/{patient_id}/treatment-stage", response_model=TreatmentStageRead)
def get_patient_treatment_stage(
    patient_id: str,
    episode_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    _: None = Depends(require_permission("patients:read")),
) -> TreatmentStageRead:
    _get_patient_or_404(db, patient_id=patient_id, organization_id=organization.id)
    resolved_episode_id = episode_id
    if resolved_episode_id is None:
        episode = _get_active_episode(db, patient_id=patient_id, organization_id=organization.id)
        if episode is None:
            return TreatmentStageRead()
        resolved_episode_id = episode.id
    else:
        episode = _get_episode_or_404(db, episode_id=resolved_episode_id, organization_id=organization.id)
        if episode.patient_id != patient_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found for patient")

    row = db.execute(
        select(PatientTreatmentStage).where(
            PatientTreatmentStage.organization_id == organization.id,
            PatientTreatmentStage.patient_id == patient_id,
            PatientTreatmentStage.episode_id == resolved_episode_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return TreatmentStageRead(episode_id=resolved_episode_id)
    return TreatmentStageRead(
        id=row.id,
        episode_id=row.episode_id,
        stage=row.stage,
        updated_by_user_id=row.updated_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/patients/{patient_id}/treatment-stage", response_model=TreatmentStageRead)
def update_patient_treatment_stage(
    patient_id: str,
    payload: TreatmentStageUpdate,
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    membership=Depends(get_current_membership),
    _: None = Depends(require_permission("patients:write")),
) -> TreatmentStageRead:
    _get_patient_or_404(db, patient_id=patient_id, organization_id=organization.id)
    stage = _normalize_choice(payload.stage, label="treatment stage", allowed=TREATMENT_STAGES)
    if payload.episode_id:
        episode = _get_episode_or_404(db, episode_id=payload.episode_id, organization_id=organization.id)
    else:
        episode = _get_active_episode(db, patient_id=patient_id, organization_id=organization.id)
        if episode is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active episode found; provide episode_id",
            )
    if episode.patient_id != patient_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found for patient")

    row = _upsert_treatment_stage(
        db,
        organization_id=organization.id,
        patient_id=patient_id,
        episode_id=episode.id,
        to_stage=stage,
        changed_by_user_id=membership.user_id,
        reason=payload.reason.strip() if payload.reason else None,
    )
    db.commit()
    db.refresh(row)

    log_event(
        db,
        action="treatment_stage.updated",
        entity_type="patient_treatment_stage",
        entity_id=row.id,
        organization_id=organization.id,
        patient_id=patient_id,
        actor=membership.user.email,
        metadata={
            "episode_id": row.episode_id,
            "stage": row.stage,
            "reason": payload.reason,
        },
    )
    return TreatmentStageRead(
        id=row.id,
        episode_id=row.episode_id,
        stage=row.stage,
        updated_by_user_id=row.updated_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/patients/{patient_id}/treatment-stage/events", response_model=list[TreatmentStageEventRead])
def list_patient_treatment_stage_events(
    patient_id: str,
    episode_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization=Depends(get_current_organization),
    _: None = Depends(require_permission("patients:read")),
) -> list[TreatmentStageEventRead]:
    _get_patient_or_404(db, patient_id=patient_id, organization_id=organization.id)
    resolved_episode_id = episode_id
    if resolved_episode_id is None:
        episode = _get_active_episode(
            db,
            patient_id=patient_id,
            organization_id=organization.id,
        )
        if episode is None:
            return []
        resolved_episode_id = episode.id
    else:
        episode = _get_episode_or_404(db, episode_id=resolved_episode_id, organization_id=organization.id)
        if episode.patient_id != patient_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found for patient")

    rows = db.execute(
        select(PatientTreatmentStageEvent)
        .where(
            PatientTreatmentStageEvent.organization_id == organization.id,
            PatientTreatmentStageEvent.patient_id == patient_id,
            PatientTreatmentStageEvent.episode_id == resolved_episode_id,
        )
        .order_by(PatientTreatmentStageEvent.created_at.desc())
    ).scalars().all()
    return rows
