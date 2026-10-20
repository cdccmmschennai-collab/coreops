"""Comp Off request workflow (Phase 3): submit, read, approve, reject, cancel.

An employee who worked an eligible non-working day asks for one working day
off in return, naming both dates. Only a project manager decides it.

ELIGIBILITY
===========
worked_date
  - not in the future (Chennai business date, the same `_today` leave and
    permission use);
  - a NON-working day by `calendar.working_days.is_working_day` - so a declared
    `working_day` override that reopens a Sunday makes it ineligible, and a
    declared holiday on a weekday makes it eligible;
  - EVIDENCE: the employee's own SUBMITTED work report for that date carrying
    at least one project task row. An automatic `week_off` / `company_holiday`
    report has zero task rows, so it is never evidence on its own; an employee
    who edits it to record real work and resubmits it does qualify, because the
    task rows are then persisted on their own report. A draft is not evidence.
  - not ruled Leave / Absent / Comp-off in attendance (a PM decision that the
    employee did not work that day).

off_date
  - strictly after today: the request must be filed before the day off;
  - a working day (a closed day has nothing to take off);
  - free: no live leave request covering it, no attendance record on it, no
    live permission on it.

Both dates must not collide with another LIVE (pending/approved) comp off of
the same employee in either column. Rejected and cancelled requests are history
and never conflict.

CONCURRENCY
===========
Creation takes `FOR NO KEY UPDATE` on the employee's row before checking
conflicts, so two submissions by the same employee serialise and the second
sees the first. The partial unique indexes of migration 0087 remain the final
guard; a lost race on them surfaces as a 409. `FOR NO KEY UPDATE` (not
`FOR UPDATE`) so ordinary foreign-key inserts against the employee - reports,
attendance - are not blocked meanwhile.

Decisions lock the request row (`FOR UPDATE`) and re-read it before checking
its status, so concurrent approve/reject/cancel calls produce exactly one
winner; the others get 409 and nothing of theirs is written.

PHASE BOUNDARY
==============
Approval records the decision only. It does NOT write attendance - the
attendance link is Phase 4 - and no notification is sent yet (there is no page
to land on until the frontend phase).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.audit.constants import AuditAction, EntityType
from app.modules.audit.service import record_audit
from app.modules.calendar.working_days import is_working_day, load_calendar_overrides
from app.modules.comp_off.models import (
    LIVE_COMP_OFF_STATUSES,
    CompOffRequest,
    CompOffStatus,
)
from app.modules.comp_off.schemas import (
    CompOffApproveBody,
    CompOffRejectBody,
    CompOffRequestCreate,
)
from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.leave.models import LeaveRequest, LeaveStatus
from app.modules.permissions.models import PermissionRequest, PermissionStatus
from app.modules.users.models import User, UserRole
from app.modules.work_reports.models import (
    DailyWorkReport,
    WorkReportStatus,
    WorkReportTask,
)
from app.shared.errors import AppError

BUSINESS_TZ = ZoneInfo("Asia/Kolkata")

# A report in one of these states is the employee's final word on the day.
# `approved` is legacy (approval was removed) but those rows are just as final.
_EVIDENCE_REPORT_STATUSES = (WorkReportStatus.submitted, WorkReportStatus.approved)

# Attendance rulings that say the employee did NOT work the worked_date.
_NOT_WORKED_ATTENDANCE = (
    AttendanceStatus.leave,
    AttendanceStatus.absent,
    AttendanceStatus.comp_off,
)

# Requests that still hold the off_date (same sets leave/permission treat as live).
_LIVE_LEAVE_STATUSES = (
    LeaveStatus.pending,
    LeaveStatus.approved,
    LeaveStatus.cancellation_requested,
)
_LIVE_PERMISSION_STATUSES = (
    PermissionStatus.pending,
    PermissionStatus.approved,
    PermissionStatus.cancellation_requested,
    PermissionStatus.recorded,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return datetime.now(BUSINESS_TZ).date()


def _long_date(value: date) -> str:
    return f"{value.day} {value:%B %Y}"


def _invalid(message: str) -> AppError:
    return AppError("validation_error", message, 422)


# ---------- authorisation ---------------------------------------------------

def _author_employee(db: Session, actor: User) -> Employee:
    me = _current_employee(db, actor)
    if me is None:
        raise _invalid("You need an employee profile to submit a comp off request.")
    return me


def _is_pm(actor: User) -> bool:
    return actor.role == UserRole.project_manager


def _assert_can_read(db: Session, actor: User, req: CompOffRequest) -> None:
    if _is_pm(actor):
        return
    me = _current_employee(db, actor)
    if me is None or req.employee_id != me.id:
        raise AppError("forbidden", "You can only view your own comp off requests.", 403)


def _assert_can_review(db: Session, actor: User, req: CompOffRequest) -> None:
    """Project managers only - no Project Head routing for comp off - and never
    one's own request. The reviewer recorded is always the caller."""
    if not _is_pm(actor):
        raise AppError(
            "forbidden", "Only a project manager can review comp off requests.", 403
        )
    me = _current_employee(db, actor)
    if me is not None and req.employee_id == me.id:
        raise AppError(
            "forbidden",
            "You can't review your own comp off request - another project manager "
            "has to decide it.",
            403,
        )


# ---------- validation -------------------------------------------------------

def _is_working_day(db: Session, value: date) -> bool:
    non_working, working_overrides = load_calendar_overrides(db, value, value)
    return is_working_day(value, non_working=non_working, working_overrides=working_overrides)


def _assert_dates(worked: date, off: date, today: date) -> None:
    if worked == off:
        raise _invalid("The day you worked and the day off must be different dates.")
    if worked > today:
        raise _invalid(
            f"{_long_date(worked)} hasn't happened yet - a comp off can only be "
            "earned for a day already worked."
        )
    if off <= today:
        raise _invalid(
            "A comp off must be requested before the day off - choose a day off "
            "after today."
        )


def _assert_worked_date_eligible(db: Session, employee_id: uuid.UUID, worked: date) -> None:
    if _is_working_day(db, worked):
        raise _invalid(
            f"{_long_date(worked)} was a working day. A comp off can only be earned "
            "for work on a holiday or non-working day."
        )
    ruling = db.execute(
        select(AttendanceRecord.status).where(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.attendance_date == worked,
            AttendanceRecord.status.in_(_NOT_WORKED_ATTENDANCE),
        )
    ).scalar_one_or_none()
    if ruling is not None:
        raise _invalid(
            f"Attendance for {_long_date(worked)} is recorded as "
            f"{ruling.value.replace('_', ' ')}, so it can't earn a comp off."
        )
    evidence = db.execute(
        select(DailyWorkReport.id)
        .join(WorkReportTask, WorkReportTask.report_id == DailyWorkReport.id)
        .where(
            DailyWorkReport.employee_id == employee_id,
            DailyWorkReport.report_date == worked,
            DailyWorkReport.status.in_(_EVIDENCE_REPORT_STATUSES),
        )
        .limit(1)
    ).scalar_one_or_none()
    if evidence is None:
        raise _invalid(
            f"No submitted work report with project activities exists for "
            f"{_long_date(worked)}. The work report for the day worked must be "
            "submitted, with the activities done, before a comp off can be requested."
        )


def _assert_off_date_free(db: Session, employee_id: uuid.UUID, off: date) -> None:
    if not _is_working_day(db, off):
        raise _invalid(
            f"{_long_date(off)} is not a working day, so there is nothing to take off."
        )
    leave = db.execute(
        select(LeaveRequest.status).where(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status.in_(_LIVE_LEAVE_STATUSES),
            LeaveRequest.start_date <= off,
            LeaveRequest.end_date >= off,
        ).limit(1)
    ).scalar_one_or_none()
    if leave is not None:
        raise _invalid(
            f"A {leave.value.replace('_', ' ')} leave request already covers "
            f"{_long_date(off)}."
        )
    recorded = db.execute(
        select(AttendanceRecord.status).where(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.attendance_date == off,
        )
    ).scalar_one_or_none()
    if recorded is not None:
        raise _invalid(
            f"Attendance for {_long_date(off)} is already recorded as "
            f"{recorded.value.replace('_', ' ')}."
        )
    permission = db.execute(
        select(PermissionRequest.status).where(
            PermissionRequest.employee_id == employee_id,
            PermissionRequest.permission_date == off,
            PermissionRequest.status.in_(_LIVE_PERMISSION_STATUSES),
        ).limit(1)
    ).scalar_one_or_none()
    if permission is not None:
        raise _invalid(
            f"A {permission.value.replace('_', ' ')} permission is already on "
            f"{_long_date(off)}."
        )


def _assert_no_comp_off_conflict(
    db: Session, employee_id: uuid.UUID, worked: date, off: date
) -> None:
    """Neither date may already be held, in EITHER column, by a live request."""
    clash = db.execute(
        select(CompOffRequest)
        .where(
            CompOffRequest.employee_id == employee_id,
            CompOffRequest.status.in_(LIVE_COMP_OFF_STATUSES),
            or_(
                CompOffRequest.worked_date.in_((worked, off)),
                CompOffRequest.off_date.in_((worked, off)),
            ),
        )
        .limit(1)
    ).scalar_one_or_none()
    if clash is None:
        return
    raise _invalid(
        f"These dates overlap an existing {clash.status.value} comp off request "
        f"(worked {_long_date(clash.worked_date)}, day off {_long_date(clash.off_date)})."
    )


# ---------- audit -----------------------------------------------------------

def _audit(db: Session, *, actor: User, action: str, req: CompOffRequest) -> None:
    """FLUSHES, never commits - lands in the caller's transaction."""
    details: dict = {
        "comp_off_request_id": str(req.id),
        "employee_id": str(req.employee_id),
        "worked_date": req.worked_date.isoformat(),
        "off_date": req.off_date.isoformat(),
        "status": req.status.value,
    }
    if req.manager_comment:
        details["comment"] = req.manager_comment
    record_audit(
        db,
        action=action,
        actor=actor,
        entity_type=EntityType.COMP_OFF_REQUEST,
        entity_id=req.id,
        details=details,
    )


# ---------- reads -----------------------------------------------------------

def _fetch(db: Session, req_id: uuid.UUID) -> CompOffRequest:
    req = db.get(CompOffRequest, req_id)
    if req is None:
        raise AppError("not_found", "Comp off request not found.", 404)
    return req


def _fetch_locked(db: Session, req_id: uuid.UUID) -> CompOffRequest:
    """`SELECT ... FOR UPDATE`, re-read, so the status check sees the latest
    committed decision. Callers check the status AFTER this."""
    req = db.execute(
        select(CompOffRequest)
        .where(CompOffRequest.id == req_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if req is None:
        raise AppError("not_found", "Comp off request not found.", 404)
    return req


def _attach_names(db: Session, rows: list[CompOffRequest]) -> None:
    """`employee_name` / `manager_name` from one batch query (non-mapped
    attributes, the same trick `permissions/service.py` uses)."""
    if not rows:
        return
    ids = {r.employee_id for r in rows} | {r.manager_id for r in rows if r.manager_id}
    people = {
        p.id: f"{p.first_name} {p.last_name}".strip()
        for p in db.execute(
            select(Employee.id, Employee.first_name, Employee.last_name).where(
                Employee.id.in_(ids)
            )
        ).all()
    }
    for r in rows:
        r.employee_name = people.get(r.employee_id)
        r.manager_name = people.get(r.manager_id) if r.manager_id else None


def list_comp_off_requests(
    db: Session,
    actor: User,
    *,
    employee_id: uuid.UUID | None,
    status: CompOffStatus | None,
    limit: int,
    offset: int,
    exclude_self: bool = False,
) -> tuple[list[CompOffRequest], int]:
    """PM: every request. Anyone else: their own only."""
    stmt = select(CompOffRequest)
    me = _current_employee(db, actor)
    if not _is_pm(actor):
        if me is None:
            return [], 0
        stmt = stmt.where(CompOffRequest.employee_id == me.id)
    if exclude_self and me is not None:
        stmt = stmt.where(CompOffRequest.employee_id != me.id)
    if employee_id is not None:
        stmt = stmt.where(CompOffRequest.employee_id == employee_id)
    if status is not None:
        stmt = stmt.where(CompOffRequest.status == status)

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = list(
        db.execute(
            stmt.order_by(CompOffRequest.created_at.desc()).limit(limit).offset(offset)
        ).scalars().all()
    )
    _attach_names(db, rows)
    return rows, total


def get_comp_off_request(db: Session, actor: User, req_id: uuid.UUID) -> CompOffRequest:
    req = _fetch(db, req_id)
    _assert_can_read(db, actor, req)
    _attach_names(db, [req])
    return req


# ---------- writes ----------------------------------------------------------

def create_comp_off_request(
    db: Session, actor: User, data: CompOffRequestCreate
) -> CompOffRequest:
    me = _author_employee(db, actor)
    _assert_dates(data.worked_date, data.off_date, _today())

    # Serialise this employee's submissions before any conflict check.
    db.execute(
        select(Employee.id).where(Employee.id == me.id).with_for_update(key_share=True)
    )
    _assert_no_comp_off_conflict(db, me.id, data.worked_date, data.off_date)
    _assert_worked_date_eligible(db, me.id, data.worked_date)
    _assert_off_date_free(db, me.id, data.off_date)

    req = CompOffRequest(
        employee_id=me.id,
        worked_date=data.worked_date,
        off_date=data.off_date,
        reason=data.reason.strip() if data.reason and data.reason.strip() else None,
        status=CompOffStatus.pending,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(req)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(
            "conflict",
            "Another comp off request for one of these dates was just submitted.",
            409,
        )
    _audit(db, actor=actor, action=AuditAction.COMP_OFF_REQUEST_SUBMIT, req=req)
    db.commit()
    db.refresh(req)
    return req


def _assert_pending(req: CompOffRequest, verb: str) -> None:
    if req.status != CompOffStatus.pending:
        raise AppError(
            "conflict",
            f"This comp off request is already {req.status.value} and can't be {verb}.",
            409,
        )


def approve_comp_off_request(
    db: Session, actor: User, req_id: uuid.UUID, data: CompOffApproveBody
) -> CompOffRequest:
    req = _fetch_locked(db, req_id)
    _assert_can_review(db, actor, req)
    _assert_pending(req, "approved")

    # Re-checked under the lock: the calendar, the report and the off day can
    # all have changed since submission. Approving on the day off itself is
    # allowed; approving a day off that has already passed is not.
    if req.off_date < _today():
        raise _invalid(
            f"The requested day off ({_long_date(req.off_date)}) has already passed. "
            "Reject the request instead."
        )
    _assert_worked_date_eligible(db, req.employee_id, req.worked_date)
    _assert_off_date_free(db, req.employee_id, req.off_date)

    reviewer = _current_employee(db, actor)
    comment = data.comment.strip() if data.comment and data.comment.strip() else None
    req.status = CompOffStatus.approved
    req.manager_id = reviewer.id if reviewer else None
    req.manager_comment = comment
    req.reviewed_at = _now()
    req.updated_by = actor.id
    db.flush()
    _audit(db, actor=actor, action=AuditAction.COMP_OFF_REQUEST_APPROVE, req=req)
    db.commit()
    db.refresh(req)
    return req


def reject_comp_off_request(
    db: Session, actor: User, req_id: uuid.UUID, data: CompOffRejectBody
) -> CompOffRequest:
    req = _fetch_locked(db, req_id)
    _assert_can_review(db, actor, req)
    _assert_pending(req, "rejected")

    reviewer = _current_employee(db, actor)
    req.status = CompOffStatus.rejected
    req.manager_id = reviewer.id if reviewer else None
    req.manager_comment = data.reason  # already trimmed and non-empty
    req.reviewed_at = _now()
    req.updated_by = actor.id
    db.flush()
    _audit(db, actor=actor, action=AuditAction.COMP_OFF_REQUEST_REJECT, req=req)
    db.commit()
    db.refresh(req)
    return req


def cancel_comp_off_request(db: Session, actor: User, req_id: uuid.UUID) -> CompOffRequest:
    """The author withdraws a PENDING request - the same one-step cancel leave
    and permission give a request nobody has decided yet. An approved request
    is not cancellable here: its policy is undecided and belongs to Phase 4."""
    req = _fetch_locked(db, req_id)
    me = _current_employee(db, actor)
    if me is None or req.employee_id != me.id:
        raise AppError("forbidden", "You can only cancel your own comp off requests.", 403)
    _assert_pending(req, "cancelled")

    req.status = CompOffStatus.cancelled
    req.updated_by = actor.id
    db.flush()
    _audit(db, actor=actor, action=AuditAction.COMP_OFF_REQUEST_CANCEL, req=req)
    db.commit()
    db.refresh(req)
    return req
