"""Project submission service."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.project_submissions.models import (
    ProjectSubmission,
    ProjectSubmissionItem,
    SubmissionStatus,
    _ALLOWED_STATUS_TRANSITIONS,
)
from app.modules.project_submissions.schemas import (
    SubmissionCreate,
    SubmissionStatusUpdate,
    SubmissionUpdate,
)
from app.modules.projects.models import Project, ProjectMember, ProjectMemberRole
from app.modules.projects.models import TimelineEventType, ProjectTimelineEvent
from app.modules.users.models import User, UserRole
from app.modules.employees.service import _current_employee
from app.shared.errors import AppError


# ── helpers ──────────────────────────────────────────────────────────────────

def _fetch_project(db: Session, project_id: uuid.UUID) -> Project:
    p = db.get(Project, project_id)
    if p is None or p.deleted_at is not None:
        raise AppError("not_found", "Project not found.", 404)
    return p


def _fetch_submission(
    db: Session, project_id: uuid.UUID, submission_id: uuid.UUID
) -> ProjectSubmission:
    sub = db.get(ProjectSubmission, submission_id)
    if sub is None or sub.project_id != project_id:
        raise AppError("not_found", "Submission not found.", 404)
    return sub


def _assert_can_read(db: Session, actor: User, project: Project) -> None:
    """PM always allowed; employees must be team_lead on this project."""
    if actor.role == UserRole.project_manager:
        return
    if actor.role == UserRole.employee:
        me = _current_employee(db, actor)
        if me is not None and db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.employee_id == me.id,
                ProjectMember.role == ProjectMemberRole.team_lead,
            )
        ).first():
            return
    raise AppError("forbidden", "Only project managers and team leads can view submissions.", 403)


def _require_pm(actor: User) -> None:
    if actor.role != UserRole.project_manager:
        raise AppError("forbidden", "Only project managers can manage submissions.", 403)


def _attach_names(db: Session, submissions: list[ProjectSubmission]) -> None:
    user_ids = {s.submitted_by for s in submissions}
    user_ids |= {s.reviewed_by for s in submissions if s.reviewed_by}
    if not user_ids:
        return
    from app.modules.users.models import User as UserModel
    rows = db.execute(select(UserModel).where(UserModel.id.in_(user_ids))).scalars().all()
    by_id = {u.id: u.email for u in rows}
    for s in submissions:
        s.submitted_by_name = by_id.get(s.submitted_by, "")  # type: ignore[attr-defined]
        s.reviewed_by_name = by_id.get(s.reviewed_by) if s.reviewed_by else None  # type: ignore[attr-defined]


def _record_timeline(
    db: Session, project_id: uuid.UUID, event_type: str, actor: User, details: dict
) -> None:
    db.add(ProjectTimelineEvent(
        project_id=project_id,
        event_type=event_type,
        actor_id=actor.id,
        actor_name=actor.email,
        details=details,
    ))


def _validate_period(start, end) -> None:
    if start is not None and end is not None and end < start:
        raise AppError("validation_error", "Period end cannot be before period start.", 422)


# ── public API ────────────────────────────────────────────────────────────────

def list_submissions(
    db: Session, actor: User, project_id: uuid.UUID
) -> list[ProjectSubmission]:
    project = _fetch_project(db, project_id)
    _assert_can_read(db, actor, project)
    rows = list(
        db.execute(
            select(ProjectSubmission)
            .where(ProjectSubmission.project_id == project_id)
            .order_by(ProjectSubmission.submission_date.desc(), ProjectSubmission.created_at.desc())
        ).scalars().all()
    )
    _attach_names(db, rows)
    return rows


def get_submission(
    db: Session, actor: User, project_id: uuid.UUID, submission_id: uuid.UUID
) -> ProjectSubmission:
    project = _fetch_project(db, project_id)
    _assert_can_read(db, actor, project)
    sub = _fetch_submission(db, project_id, submission_id)
    _attach_names(db, [sub])
    return sub


def create_submission(
    db: Session, actor: User, project_id: uuid.UUID, data: SubmissionCreate
) -> ProjectSubmission:
    _require_pm(actor)
    _fetch_project(db, project_id)
    _validate_period(data.period_start, data.period_end)

    sub = ProjectSubmission(
        project_id=project_id,
        submission_date=data.submission_date,
        period_start=data.period_start,
        period_end=data.period_end,
        status=SubmissionStatus.draft.value,
        notes=data.notes,
        submitted_by=actor.id,
    )
    db.add(sub)
    db.flush()

    for item_in in data.items:
        db.add(ProjectSubmissionItem(
            submission_id=sub.id,
            activity_type_id=item_in.activity_type_id,
            activity_label=item_in.activity_label,
            quantity=item_in.quantity,
            unit=item_in.unit,
        ))

    _record_timeline(db, project_id, TimelineEventType.SUBMISSION_CREATED, actor, {
        "submission_id": str(sub.id),
        "period_start": data.period_start.isoformat(),
        "period_end": data.period_end.isoformat(),
    })
    db.commit()
    db.refresh(sub)
    _attach_names(db, [sub])
    return sub


def update_submission(
    db: Session, actor: User, project_id: uuid.UUID,
    submission_id: uuid.UUID, data: SubmissionUpdate
) -> ProjectSubmission:
    _require_pm(actor)
    sub = _fetch_submission(db, project_id, submission_id)
    if sub.status != SubmissionStatus.draft.value:
        raise AppError("validation_error", "Only draft submissions can be edited.", 422)

    if data.submission_date is not None:
        sub.submission_date = data.submission_date
    if data.period_start is not None:
        sub.period_start = data.period_start
    if data.period_end is not None:
        sub.period_end = data.period_end
    if data.notes is not None:
        sub.notes = data.notes

    _validate_period(sub.period_start, sub.period_end)

    if data.items is not None:
        # Replace all items
        db.execute(
            delete(ProjectSubmissionItem).where(
                ProjectSubmissionItem.submission_id == sub.id
            )
        )
        for item_in in data.items:
            db.add(ProjectSubmissionItem(
                submission_id=sub.id,
                activity_type_id=item_in.activity_type_id,
                activity_label=item_in.activity_label,
                quantity=item_in.quantity,
                unit=item_in.unit,
            ))

    sub.updated_at = datetime.now(timezone.utc)  # type: ignore[assignment]
    db.add(sub)
    _record_timeline(db, project_id, TimelineEventType.SUBMISSION_UPDATED, actor, {
        "submission_id": str(sub.id),
        "field": "details",
    })
    db.commit()
    db.refresh(sub)
    _attach_names(db, [sub])
    return sub


def update_submission_status(
    db: Session, actor: User, project_id: uuid.UUID,
    submission_id: uuid.UUID, data: SubmissionStatusUpdate
) -> ProjectSubmission:
    _require_pm(actor)
    sub = _fetch_submission(db, project_id, submission_id)
    current = SubmissionStatus(sub.status)

    if data.status == current:
        _attach_names(db, [sub])
        return sub

    allowed = _ALLOWED_STATUS_TRANSITIONS.get(current, set())
    if data.status not in allowed:
        raise AppError(
            "validation_error",
            f"Cannot transition from '{current.value}' to '{data.status.value}'.",
            422,
        )

    sub.status = data.status.value
    if data.status in (SubmissionStatus.approved, SubmissionStatus.rejected):
        sub.reviewed_by = actor.id
        sub.reviewed_at = datetime.now(timezone.utc)
        sub.review_note = data.review_note
    elif data.status == SubmissionStatus.draft:
        # Re-open: clear review fields
        sub.reviewed_by = None
        sub.reviewed_at = None
        sub.review_note = None

    sub.updated_at = datetime.now(timezone.utc)  # type: ignore[assignment]
    db.add(sub)
    _record_timeline(db, project_id, TimelineEventType.SUBMISSION_UPDATED, actor, {
        "submission_id": str(sub.id),
        "field": "status",
        "old": current.value,
        "new": data.status.value,
    })
    db.commit()
    db.refresh(sub)
    _attach_names(db, [sub])
    return sub


def delete_submission(
    db: Session, actor: User, project_id: uuid.UUID, submission_id: uuid.UUID
) -> None:
    _require_pm(actor)
    sub = _fetch_submission(db, project_id, submission_id)
    if sub.status != SubmissionStatus.draft.value:
        raise AppError("validation_error", "Only draft submissions can be deleted.", 422)
    db.delete(sub)
    db.commit()
