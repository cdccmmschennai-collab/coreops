"""Leave Request service: RBAC-scoped reads + employee writes + manager review.

RBAC:
  admin    full access â€” list all, approve/reject any
  manager  list own + team (direct reports); approve/reject team requests
  employee list own requests; create/update/cancel own pending

Workflow:
  pending  â†’ approved   (manager/admin)
  pending  â†’ rejected   (manager/admin, comment optional)
  pending  â†’ cancelled  (employee, own pending only)
  approved â†’ cancellation_requested  (employee, own leave that hasn't ended)
  cancellation_requested â†’ cancelled (manager approves the withdrawal)
  cancellation_requested â†’ approved  (manager keeps the leave)
  rejected â†’ (re-open by editing â†’ back to pending? No: employee must create new)

Every status change re-reads its row under `SELECT ... FOR UPDATE` before
checking the status, so a concurrent approve/cancel pair resolves to exactly
one winner rather than both seeing `pending`.

PHASE 10: AN APPROVAL NOW MOVES REAL STATE
==========================================
Approving leave marks each working day of the range `leave` in
`attendance_records` and draws the same number of days out of the employee's
leave balance; cancelling an approved leave reverses both. That is a deliberate
change from the earlier behaviour, where attendance and balances were maintained
entirely by hand and a leave decision changed nothing outside this table - an
approved leave simply never reached the employee's calendar, which is what
Phase 10 exists to fix.

All of it lives in `leave/effects.py`, which owns the day-counting rule, the
skip-don't-overwrite rule and the balance movement. Nothing in this file writes
to those tables directly, and every decision flushes its effect inside the same
transaction as the status change, so a leave is never approved without its days
being marked.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import authz
from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.audit.constants import AuditAction, EntityType
from app.modules.audit.service import record_audit
from app.modules.biometric.classification import DayClassification
from app.modules.biometric.service import settled_present_days
from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.leave.effects import (
    MAX_LEAVE_RANGE_DAYS,
    apply_leave_approved,
    leave_working_days,
    plan_leave_days,
    reverse_leave_approved,
)
from app.modules.leave.classification import (
    classification_label,
    classify_leave,
)
from app.modules.leave.models import RETIRED_LEAVE_TYPE, LeaveRequest, LeaveStatus
from app.modules.leave import email as leave_email
from app.modules.leave import routing
from app.modules.leave.recipients import leave_request_path, resolve_in_app_recipient
# Read-only: the submission notification is the durable record of WHO a settled
# request was routed to. Safe at module level - `notifications.service` imports
# only its own models and `users.models`, so there is no cycle back to here.
from app.modules.notifications import service as notifications_service
from app.modules.leave.schemas import (
    AttendanceSummaryRequest,
    DeliverableConflictOut,
    LeaveAttendanceSummaryOut,
    LeaveDeliverableImpactOut,
    LeaveRequestCreate,
    LeaveRequestUpdate,
    LeaveReviewBody,
)
from app.modules.users.models import User, UserRole
from app.modules.work_reports.auto_reports import reconcile_auto_leave_reports
from app.shared.errors import AppError

# Number of calendar days before/after a deliverable's planned date that a
# leave day must fall within to count as a Deliverable Impact.
DELIVERABLE_IMPACT_WINDOW = timedelta(days=2)

# CoreOps runs on a single business calendar. "Has this leave already ended?"
# must be judged on the Chennai business day: at 00:30 IST the server's UTC date
# is still yesterday, which would keep a finished leave cancellable.
BUSINESS_TZ = ZoneInfo("Asia/Kolkata")


# Attendance statuses that mean the employee actually worked that day â€” you
# can't take (or be granted) leave for a day you've already attended.
_WORKED_ATTENDANCE = (AttendanceStatus.present, AttendanceStatus.half_day)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return datetime.now(BUSINESS_TZ).date()


def _long_date(value: date) -> str:
    # Built from .day rather than a %-d/%#d directive, which is platform-specific.
    return f"{value.day} {value:%B %Y}"


def _period(req: LeaveRequest) -> str:
    """`3 August 2026`, or `28 July 2026 - 30 July 2026` for a range."""
    start = _long_date(req.start_date)
    if req.start_date == req.end_date:
        return start
    return f"{start} - {_long_date(req.end_date)}"


def _worked_attendance_dates(
    db: Session, employee_id: uuid.UUID, start_date: date, end_date: date
) -> list[date]:
    """Dates in [start_date, end_date] where the employee is marked present /
    working â€” the days a leave request must not cover."""
    return list(
        db.execute(
            select(AttendanceRecord.attendance_date)
            .where(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.status.in_(_WORKED_ATTENDANCE),
                AttendanceRecord.attendance_date >= start_date,
                AttendanceRecord.attendance_date <= end_date,
            )
            .order_by(AttendanceRecord.attendance_date)
        ).scalars()
    )


def _format_dates(dates: list[date]) -> str:
    return ", ".join(d.isoformat() for d in dates)


def _biometric_present_days(
    db: Session, employee_id: uuid.UUID, days: list[date]
) -> dict[date, DayClassification]:
    """Which of `days` the DEVICE settled as a full day's attendance.

    The second half of "you can't take leave for a day you worked". The check
    above it reads `attendance_records` - a human's ruling. This one reads the
    biometric evidence for the days that carry NO ruling yet, which is the gap
    that let a fully-punched day be approved as leave: nobody had marked it, so
    nothing objected, and the day ended up recorded as Leave with the punches
    still sitting under it.

    The caller passes the days the leave would actually CLAIM, never the raw
    range: a punch on a Sunday or a company holiday inside a range costs the
    employee nothing and marks nothing, so it must not refuse their week.

    The verdict comes from `biometric.settled_present_days`, which runs the same
    boundary and classification rules the employee's own calendar renders. Only a
    `present` day counts: one punch, or a day the shift could not be compared
    against, is unsettled, and refusing leave on unsettled evidence would be a
    guess.
    """
    if not days:
        return {}
    settled = settled_present_days(
        db, employee_id=employee_id, date_from=min(days), date_to=max(days)
    )
    wanted = set(days)
    return {day: verdict for day, verdict in settled.items() if day in wanted}


def _format_present_days(settled: dict[date, DayClassification]) -> str:
    """`"12 August 2026 (09:10 AM - 05:54 PM)"`, so the employee can check it.

    The punch window is named rather than just the date: a bare "you were present
    on 12 August" is unarguable-with, while the two times let someone recognise
    the day - or see immediately that the device recorded somebody else's finger.
    """
    parts: list[str] = []
    for day in sorted(settled):
        verdict = settled[day]
        window = ""
        first_in, last_out = verdict.first_in, verdict.last_out
        if first_in is not None and last_out is not None:
            window = (
                f" ({first_in.astimezone(BUSINESS_TZ):%I:%M %p}"
                f" - {last_out.astimezone(BUSINESS_TZ):%I:%M %p})"
            )
        parts.append(f"{_long_date(day)}{window}")
    return ", ".join(parts)


def _assert_not_biometrically_present(
    db: Session, employee_id: uuid.UUID, start_date: date, end_date: date
) -> None:
    """Refuse a leave range covering a day the device settled as a full day.

    Raised at create and at edit, and again at approval by
    `_assert_approvable_against_biometric` - the evidence can arrive between the
    two, and the day must not be marked Leave on the strength of a check that ran
    before the punches synced.

    The employee is told which day and which punch window, because the only
    honest way out of this block is to correct the record: if the device is
    wrong, that is a biometric review, not a leave request.
    """
    settled = _biometric_present_days(
        db, employee_id, leave_working_days(db, start_date, end_date)
    )
    if not settled:
        return
    raise AppError(
        "validation_error",
        f"The biometric record shows you were present on "
        f"{_format_present_days(settled)} - you can't request leave for a day the "
        "device recorded a full day's attendance. Ask your manager to correct the "
        "attendance record first if this is wrong.",
        422,
    )


def _assert_approvable_against_biometric(
    db: Session, employee_id: uuid.UUID, days: list[date]
) -> None:
    """The same block, in the manager's words, at the moment of approval.

    Separate from the employee-facing message on purpose: a PM reading their
    review queue needs to know what to DO with the request, and the answer is
    reject it - approving would write a Leave day directly on top of a day the
    device says the person worked.

    `days` is what the approval is actually about to mark, reusing the plan the
    caller already computed. A day that already carries somebody's ruling is not
    checked here: the approval will not touch it, so no Leave row can land on top
    of its punches.
    """
    settled = _biometric_present_days(db, employee_id, days)
    if not settled:
        return
    raise AppError(
        "validation_error",
        f"The biometric record shows this employee was present on "
        f"{_format_present_days(settled)}; their leave can't be approved. Reject "
        "the request, or correct the attendance record first.",
        422,
    )


def _push(db: Session, user_id: uuid.UUID, type_: str, title: str, message: str,
          entity_id: uuid.UUID | None = None, target_url: str | None = None) -> None:
    try:
        from app.modules.notifications.service import create_notification
        create_notification(db, user_id=user_id, type_=type_, title=title, message=message,
                            entity_type="leave_request", entity_id=entity_id,
                            target_url=target_url)
        db.commit()
    except Exception:
        db.rollback()


def _notify_routed_approver(db: Session, employee: Employee, req: LeaveRequest,
                            type_: str, title: str, message: str,
                            queue: str | None = None) -> None:
    """Notify whoever this request is routed to: the CURRENT Head of
    `req.routed_project_id` if one is assigned (and isn't the requester
    themself), else the employee's reporting PM.

    Takes the first candidate with a login to deliver to, then STOPS - exactly
    one person is notified, never all candidates. A Head with no linked user
    account falls through to the PM, which is the rule this function has always
    applied; only the identity of that fallback rung changed (line manager ->
    reporting PM), so that the person notified is a person who can actually
    approve the request.

    That selection now lives in `recipients.resolve_in_app_recipient` rather than
    inline here, because `_attach_routed_to` has to answer the same question for
    the detail page's "Routed to" line. Same function, same answer.
    """
    candidate = resolve_in_app_recipient(db, employee, req)
    if candidate is None:
        return
    # Both rungs are approvers, so both open the request's own detail page with
    # Team approvals behind it - the queue they were working stays the Back
    # target, and the actions are on the page itself.
    _push(db, candidate.employee.user_id, type_, title, message, req.id,
          leave_request_path(req, view="team", queue=queue or "pending"))


def _notify_employee(db: Session, employee_id: uuid.UUID, type_: str, title: str,
                     message: str, entity_id: uuid.UUID | None = None,
                     target_url: str | None = None) -> None:
    emp = db.get(Employee, employee_id)
    if emp is None or emp.user_id is None:
        return
    _push(db, emp.user_id, type_, title, message, entity_id, target_url)


def _audit_decision(
    db: Session,
    *,
    actor: User,
    action: str,
    req: LeaveRequest,
    comment: str | None = None,
    effect=None,
) -> None:
    """Record one leave decision centrally. FLUSHES, never commits.

    Goes through the same `record_audit` every other CoreOps module uses, so
    leave decisions land in the existing Settings audit trail and its filters
    rather than in a second log of their own. The details carry what the request
    row cannot: the day count actually marked, the days skipped, and the balance
    movement - facts the next decision would otherwise overwrite.
    """
    details: dict = {
        "leave_request_id": str(req.id),
        "employee_id": str(req.employee_id),
        # Normal / Special, derived from the same working-day count the decision
        # is being taken on - not the retired stored category.
        "classification": classify_leave(
            len(leave_working_days(db, req.start_date, req.end_date))
        ).value,
        "start_date": req.start_date.isoformat(),
        "end_date": req.end_date.isoformat(),
        "status": req.status.value,
    }
    if comment and comment.strip():
        details["comment"] = comment.strip()
    if effect is not None:
        details["days_marked"] = effect.day_count
        if effect.skipped:
            details["days_skipped"] = [d.isoformat() for d in effect.skipped]
        if effect.balance_before is not None:
            details["balance_before"] = str(effect.balance_before)
            details["balance_after"] = str(effect.balance_after)

    record_audit(
        db,
        action=action,
        actor=actor,
        entity_type=EntityType.LEAVE_REQUEST,
        entity_id=req.id,
        details=details,
    )


def _effect_sentence(effect, req: LeaveRequest) -> str:
    """The balance movement, appended to the employee's notification.

    Only stated when something actually moved - an unpaid leave, or an approval
    where every day already had an official record, says nothing rather than
    reporting a deduction of zero.
    """
    if effect.balance_before is None or not effect.day_count:
        return ""
    days = effect.day_count
    word = "day" if days == 1 else "days"
    return (
        f" {days} {word} deducted from your leave balance "
        f"({effect.balance_before:g} to {effect.balance_after:g})."
    )


def _restored_sentence(effect) -> str:
    if effect.balance_before is None or not effect.day_count:
        return ""
    days = effect.day_count
    word = "day" if days == 1 else "days"
    return (
        f" {days} {word} restored to your leave balance "
        f"({effect.balance_before:g} to {effect.balance_after:g})."
    )


def _team_ids(manager_employee_id: uuid.UUID):
    return select(Employee.id).where(
        Employee.manager_id == manager_employee_id, Employee.deleted_at.is_(None)
    )


# ---------- scope helpers --------------------------------------------------

def _apply_scope(db: Session, actor: User, stmt):
    if actor.role == UserRole.project_manager:
        return stmt, True
    me = _current_employee(db, actor)
    if me is None:
        return stmt, False
    head_project_ids = authz.reviewable_project_ids(db, actor)
    if head_project_ids:
        return (
            stmt.where(
                or_(
                    LeaveRequest.employee_id == me.id,
                    LeaveRequest.routed_project_id.in_(head_project_ids),
                )
            ),
            True,
        )
    return stmt.where(LeaveRequest.employee_id == me.id), True


def _assert_can_read(db: Session, actor: User, req: LeaveRequest) -> None:
    if actor.role == UserRole.project_manager:
        return
    if req.routed_project_id is not None and authz.can_review_report(
        db, actor, {req.routed_project_id}
    ):
        return
    me = _current_employee(db, actor)
    if me is None:
        raise AppError("forbidden", "Not permitted.", 403)
    if req.employee_id == me.id:
        return
    raise AppError("forbidden", "You can only view your own leave requests.", 403)


def _assert_can_review(db: Session, actor: User, req: LeaveRequest | None = None) -> None:
    """Who may rule on a leave request - enforced here, in the backend, on every
    decision path. The frontend hides the buttons; this is what actually stops it.

    PM (any request) or the CURRENT Head of the request's routed project may
    review. `authz.can_review_report` already encodes exactly that rule (it's
    the same helper Work Reports uses) so this stays a one-line delegation
    rather than a second copy of the PM-or-Head check.

    NOBODY REVIEWS THEIR OWN LEAVE, including a project manager or a Head:
    project managers and Heads are employees too and file their own requests,
    so without the second check either could approve their own leave and grant
    themselves the balance. `req` is therefore passed on every decision path -
    approve, reject, and both cancellation decisions.
    """
    project_ids = {req.routed_project_id} if (req is not None and req.routed_project_id is not None) else set()
    if not authz.can_review_report(db, actor, project_ids):
        raise AppError(
            "forbidden",
            "Only a project manager or this request's assigned Project Head can review it.",
            403,
        )
    if req is None:
        return
    me = _current_employee(db, actor)
    if me is not None and req.employee_id == me.id:
        raise AppError(
            "forbidden",
            "You can't review your own leave request - another reviewer has to decide it.",
            403,
        )


# Statuses that still represent a live claim on the employee's dates. A rejected
# or cancelled request is not an absence any more, so it never blocks a new one.
_ACTIVE_LEAVE_STATUSES = (
    LeaveStatus.pending,
    LeaveStatus.approved,
    LeaveStatus.cancellation_requested,
)


def _assert_no_overlap(
    db: Session,
    employee_id: uuid.UUID,
    start_date: date,
    end_date: date,
    *,
    exclude_id: uuid.UUID | None = None,
) -> None:
    """Reject a request whose dates already have a live request on them.

    Covers the exact-duplicate case and every partial overlap with it: two ranges
    intersect exactly when each starts on or before the other ends. Without this
    an employee could file the same week five times, and each approval would
    deduct the balance again.
    """
    stmt = select(LeaveRequest).where(
        LeaveRequest.employee_id == employee_id,
        LeaveRequest.status.in_(_ACTIVE_LEAVE_STATUSES),
        LeaveRequest.start_date <= end_date,
        LeaveRequest.end_date >= start_date,
    )
    if exclude_id is not None:
        stmt = stmt.where(LeaveRequest.id != exclude_id)
    clash = db.execute(stmt.order_by(LeaveRequest.start_date).limit(1)).scalar_one_or_none()
    if clash is None:
        return
    raise AppError(
        "validation_error",
        f"You already have a {clash.status.value.replace('_', ' ')} leave request "
        f"covering {_period(clash)}.",
        422,
    )


def _fetch(db: Session, req_id: uuid.UUID) -> LeaveRequest:
    req = db.get(LeaveRequest, req_id)
    if req is None:
        raise AppError("not_found", "Leave request not found.", 404)
    return req


def _fetch_locked(db: Session, req_id: uuid.UUID) -> LeaveRequest:
    """Load the request with `SELECT ... FOR UPDATE`.

    The lock is held until the surrounding commit, so a second writer racing on
    the same request blocks here and then re-reads the status the winner wrote â€”
    which its own status check then rejects. Callers must therefore lock BEFORE
    validating status, never after.
    """
    req = db.execute(
        select(LeaveRequest).where(LeaveRequest.id == req_id).with_for_update()
    ).scalar_one_or_none()
    if req is None:
        raise AppError("not_found", "Leave request not found.", 404)
    return req


def _author_employee(db: Session, actor: User) -> Employee:
    me = _current_employee(db, actor)
    if me is None:
        raise AppError(
            "validation_error",
            "You need an employee profile to submit a leave request.",
            422,
        )
    return me


# ---------- reads ----------------------------------------------------------

def list_leave_requests(
    db: Session,
    actor: User,
    *,
    employee_id: uuid.UUID | None,
    status: LeaveStatus | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    offset: int,
    exclude_self: bool = False,
) -> tuple[list[LeaveRequest], int]:
    stmt = select(LeaveRequest)
    stmt, allowed = _apply_scope(db, actor, stmt)
    if not allowed:
        return [], 0

    if exclude_self:
        me = _current_employee(db, actor)
        if me is not None:
            stmt = stmt.where(LeaveRequest.employee_id != me.id)

    if employee_id is not None:
        stmt = stmt.where(LeaveRequest.employee_id == employee_id)
    if status is not None:
        stmt = stmt.where(LeaveRequest.status == status)
    # THE DATE WINDOW IS AN OVERLAP, NOT A CONTAINMENT.
    #
    # A leave request matches when its LEAVE PERIOD intersects [date_from,
    # date_to] - `start <= window_end AND end >= window_start`, the same
    # two-sided test `_assert_no_overlap` above uses to decide two ranges clash.
    # `created_at` is never consulted: the question the All-leave window answers
    # is "who was away in September", and a request filed in August for
    # September is exactly what that has to return.
    #
    # It used to be containment (`start >= from AND end <= to`), which silently
    # dropped every absence straddling either edge of the window - the 30 Aug -
    # 2 Sep leave vanished from a September filter. Nothing consumed these two
    # parameters before this phase (no frontend call site, no test), so the
    # correction changes no existing behaviour.
    #
    # Either bound may be given alone: `from` on its own means "still running on
    # or after this date", `to` on its own "had started by this date".
    if date_from is not None:
        stmt = stmt.where(LeaveRequest.end_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(LeaveRequest.start_date <= date_to)

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(LeaveRequest.created_at.desc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    _attach_employee_names(db, rows)
    return list(rows), total


def get_leave_request(db: Session, actor: User, req_id: uuid.UUID) -> LeaveRequest:
    req = _fetch(db, req_id)
    _assert_can_read(db, actor, req)
    _attach_employee_names(db, [req])
    _attach_routed_to(db, req)
    return req


def _attach_routed_to(db: Session, req: LeaveRequest) -> None:
    """Set `.routed_to_name` - who a STILL-PENDING request is waiting on.

    Same non-mapped-attribute trick as `_attach_employee_names`, and the same
    reason: routing is not a column. `routed_project_id` is, but the person is
    derived from it fresh on every read by `recipients.resolve_in_app_recipient`
    - the routed project's CURRENT Head, else the requester's reporting PM, first
    one with a login. That is the whole point of deriving rather than storing: a
    Head reassigned after the request was filed is honoured here exactly as it is
    at approval time, and no migration is needed to say who is holding a request.

    IT IS THE SAME FUNCTION THE NOTIFICATION WALKS. The employee reading "Routed
    to NAINAR B" is being told the name of the person whose bell actually rang.

    DETAIL-PAGE ONLY. Only the detail endpoint calls this. Resolving a Head and
    a PM per row would add two queries to every row of a 20-row All-leave page
    for a column that page does not have.

    ONCE DECIDED, THE ANSWER STOPS BEING DERIVED. A settled request still shows
    who it went to - "Routed to" and "Approved by" are two different facts and
    the card shows both - but re-deriving the routed person after the fact would
    name whoever heads that project TODAY, which is not who the request was sent
    to. So the settled answer comes from the SUBMISSION NOTIFICATION actually
    delivered at submission time: one row, written once, to exactly the person
    the routing chose. That is the only historically accurate record there is,
    and reading it needs no new column and no migration.

    A request awaiting a CANCELLATION decision, or already cancelled, is left
    alone: those statuses show no actor row at all (see `leaveActorRows` in the
    frontend), so there is nothing to resolve.

    None is a legitimate answer - an unrouted request whose requester has no
    reporting PM, one whose only candidate has no login, or a settled request
    whose submission notification was never written - and the page simply omits
    the row.
    """
    req.routed_to_name = None
    if req.status == LeaveStatus.pending:
        employee = db.get(Employee, req.employee_id)
        if employee is None:
            return
        recipient = resolve_in_app_recipient(db, employee, req)
        if recipient is not None:
            req.routed_to_name = recipient.employee.full_name
        return

    if req.status not in (LeaveStatus.approved, LeaveStatus.rejected):
        return
    user_id = notifications_service.first_notified_user_id(
        db,
        type_="leave_submitted",
        entity_type="leave_request",
        entity_id=req.id,
    )
    if user_id is None:
        return
    recipient_employee = db.execute(
        select(Employee).where(Employee.user_id == user_id)
    ).scalars().first()
    if recipient_employee is not None:
        req.routed_to_name = recipient_employee.full_name


def _attach_employee_names(db: Session, rows: list[LeaveRequest]) -> None:
    """Set `.employee_name` and `.manager_name` on each row from one batch query.

    `LeaveRequest` has no ORM relationship to `Employee` (by design - a bare
    `employee_id` column), so the name isn't a mapped attribute. Setting it here
    is still legal: Pydantic v2's `from_attributes` reads it off the instance at
    validation time in the router, the same pattern `deliverable_impacts` already
    uses for `DeliverableConflictOut.employee_name` below.

    This makes the Employee lookup a backend concern for every caller of these
    two functions, rather than depending on `GET /employees`, which returns only
    the caller's own row for a plain-employee-role actor (which a Project Head
    still is) - the bug this exists to fix.

    `manager_name` is THE DECISION ACTOR, and it is not new information: both
    `approve_leave_request` and `reject_leave_request` already stamp
    `req.manager_id` with the reviewing employee at decision time, precisely so
    the ruling survives a later change of reporting line. All that was missing
    was the human-readable name, so the two ids are resolved together in the one
    query that was already being run rather than through a second column, a
    second table or a migration.

    Both names come out of the SAME id->name map, so the actor is rendered
    exactly as the requester is. NULL for a request nobody has ruled on yet, and
    for the historical rows that were decided before `manager_id` was recorded.
    Note that a request approved and later CANCELLED keeps the approver's id -
    that is the truth of what happened - so "which statuses show an actor" is a
    display decision, taken once in the frontend's `leaveDecisionActor`.
    """
    if not rows:
        return
    people_ids = {r.employee_id for r in rows}
    people_ids |= {r.manager_id for r in rows if r.manager_id is not None}
    names = {
        row.id: f"{row.first_name} {row.last_name}".strip()
        for row in db.execute(
            select(Employee.id, Employee.first_name, Employee.last_name).where(
                Employee.id.in_(people_ids)
            )
        ).all()
    }
    for r in rows:
        r.employee_name = names.get(r.employee_id)
        r.manager_name = names.get(r.manager_id) if r.manager_id is not None else None


def attach_computed_fields(db: Session, rows: list[LeaveRequest]) -> None:
    """Set `.working_days` and `.classification` on each row.

    Same non-mapped-attribute trick as `_attach_employee_names` above, and the
    same reason - neither is a column. The count is a question for the company
    calendar, and the answer comes from `effects.leave_working_days`, which is
    what an approval charges against, so the number the Leave Detail page shows
    and the number deducted from the employee's balance are the same
    calculation: 28-31 August 2026 is 3, because the 5th Saturday works and the
    Sunday does not. Nothing here re-implements the weekend/holiday rule.

    `.classification` is Normal or Special, read straight off that count by
    `classification.classify_leave`. Deriving it here rather than storing it is
    what makes a historical request classify correctly with no backfill, and
    what stops the answer going stale when the dates or the calendar move.

    Called by the router for every `LeaveRequestOut` it builds. One overrides
    query per row; the pages that use it are small and the alternative was a
    second copy of the day-walking loop.
    """
    for r in rows:
        r.working_days = len(leave_working_days(db, r.start_date, r.end_date))
        r.classification = classify_leave(r.working_days)


# ---------- employee writes -----------------------------------------------

def create_leave_request(
    db: Session, actor: User, data: LeaveRequestCreate
) -> LeaveRequest:
    me = _author_employee(db, actor)
    if data.end_date < data.start_date:
        raise AppError("validation_error", "End date cannot be before start date.", 422)

    worked = _worked_attendance_dates(db, me.id, data.start_date, data.end_date)
    if worked:
        raise AppError(
            "validation_error",
            f"You're marked present on {_format_dates(worked)} - you can't request "
            "leave for a day you've already attended.",
            422,
        )
    _assert_not_biometrically_present(db, me.id, data.start_date, data.end_date)
    _assert_no_overlap(db, me.id, data.start_date, data.end_date)

    req = LeaveRequest(
        employee_id=me.id,
        # The retired category column, which is NOT NULL. Nothing reads it back
        # as a classification - see `models.RETIRED_LEAVE_TYPE`.
        leave_type=RETIRED_LEAVE_TYPE,
        start_date=data.start_date,
        end_date=data.end_date,
        reason=data.reason,
        status=LeaveStatus.pending,
        routed_project_id=routing.resolve_routed_project(db, me.id, data.start_date),
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    classification = classify_leave(
        len(leave_working_days(db, req.start_date, req.end_date))
    )
    _notify_routed_approver(
        db, me, req, "leave_submitted",
        f"{me.full_name} submitted a leave request",
        f"{me.full_name} requested {classification_label(classification)} "
        f"from {data.start_date} to {data.end_date}.",
    )
    # Email the same approver the notification above just reached - both walk
    # `resolve_leave_recipients`, so they cannot route differently. Placed AFTER
    # the commit and after the in-app push on purpose: the request is already
    # saved and the bell has already rung, so nothing this call does - including
    # an unreachable broker - can cost either of them. It never raises.
    #
    # Submission is the ONLY leave event that emails. Approve, reject, cancel and
    # the cancellation decisions stay in-app, which is why this sits here rather
    # than in `_push` or `_notify_routed_approver`, both shared by those events.
    leave_email.send_submission_email(db, me, req)
    return req


def update_leave_request(
    db: Session, actor: User, req_id: uuid.UUID, data: LeaveRequestUpdate
) -> LeaveRequest:
    me = _author_employee(db, actor)
    req = _fetch_locked(db, req_id)
    if req.employee_id != me.id:
        raise AppError("forbidden", "You can only edit your own leave requests.", 403)
    if req.status != LeaveStatus.pending:
        raise AppError("forbidden", "Only pending requests can be edited.", 403)

    fields = data.model_dump(exclude_unset=True)
    new_start = fields.get("start_date", req.start_date)
    new_end = fields.get("end_date", req.end_date)
    if new_end < new_start:
        raise AppError("validation_error", "End date cannot be before start date.", 422)

    worked = _worked_attendance_dates(db, me.id, new_start, new_end)
    if worked:
        raise AppError(
            "validation_error",
            f"You're marked present on {_format_dates(worked)} - you can't request "
            "leave for a day you've already attended.",
            422,
        )
    _assert_not_biometrically_present(db, me.id, new_start, new_end)
    _assert_no_overlap(db, me.id, new_start, new_end, exclude_id=req.id)

    for key, value in fields.items():
        setattr(req, key, value)
    req.updated_by = actor.id
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def _reconcile_auto_leave_reports(db: Session, req: LeaveRequest) -> None:
    """PHASE 3F: take back the automatic leave reports this request produced.

    Called only from the transitions that actually END the absence, and only
    after the new status is on the object, so the reconciler reads the decision
    that was just made. FLUSHES via the reconciler, never commits: the status
    change and the reports it withdraws land in one transaction, exactly as the
    attendance rows above them do.

    EVERY CALENDAR DAY of the range is offered, not `leave_working_days`. The
    calendar the 01:00 generator saw is not necessarily today's - a day declared
    a company holiday after the report was written would drop out of the working
    set and leave a locked report behind with nothing left to remove it. Offering
    a day that never had a report costs nothing: `reconcile_auto_leave_reports`
    matches on `origin = auto AND day_status = leave` for this employee alone, so
    a day with no automatic report, an employee-authored report, or an automatic
    week-off report simply is not found.

    Bounded by the leave module's own `MAX_LEAVE_RANGE_DAYS`, the same guard
    `effects._range_days` puts on a malformed range.
    """
    span = (req.end_date - req.start_date).days
    if span < 0:
        return
    span = min(span, MAX_LEAVE_RANGE_DAYS - 1)
    reconcile_auto_leave_reports(
        db,
        [
            (req.employee_id, req.start_date + timedelta(days=offset))
            for offset in range(span + 1)
        ],
        commit=False,
    )


def cancel_leave_request(db: Session, actor: User, req_id: uuid.UUID) -> LeaveRequest:
    """pending -> cancelled, by the employee who filed it.

    The row is kept so the request stays in the employee's history; it simply
    stops matching the pending queries the manager's queue is built from.
    """
    me = _author_employee(db, actor)
    # Locked before the status check so an employee cancelling and a manager
    # approving the same request cannot both win the race.
    req = _fetch_locked(db, req_id)
    if req.employee_id != me.id:
        raise AppError("forbidden", "You can only cancel your own leave requests.", 403)
    if req.status != LeaveStatus.pending:
        raise AppError("conflict", "Only pending requests can be cancelled.", 409)

    req.status = LeaveStatus.cancelled
    req.updated_by = actor.id
    db.add(req)
    # A pending request never marked a day or moved a balance, so cancelling it
    # has nothing to reverse (section 12D).
    #
    # PHASE 3F: the direct pending -> cancelled path, hooked for completeness.
    # It is a no-op BY CONSTRUCTION today - only `approved` leave generates an
    # automatic report (`auto_reports.AUTO_LEAVE_STATUSES`), and a request that
    # reaches here was never approved - but this is a path on which an absence
    # ceases to exist, and the rule is that every such path reconciles. The cost
    # when there is nothing to find is one indexed SELECT.
    _reconcile_auto_leave_reports(db, req)
    _audit_decision(
        db, actor=actor, action=AuditAction.LEAVE_REQUEST_CANCEL, req=req
    )
    db.commit()
    db.refresh(req)
    _notify_routed_approver(
        db, me, req, "leave_cancelled",
        f"{me.full_name} cancelled a leave request",
        f"{me.full_name} cancelled their leave request ({req.start_date} to {req.end_date}).",
    )
    return req


# ---------- approved-leave cancellation ------------------------------------

def request_leave_cancellation(
    db: Session, actor: User, req_id: uuid.UUID
) -> LeaveRequest:
    """approved -> cancellation_requested, by the employee who filed it.

    The leave stays active until a manager decides â€” this only puts it in their
    queue. Leave that has already finished is out of scope: there is nothing
    left to withdraw, and correcting the record is an attendance job.
    """
    me = _author_employee(db, actor)
    req = _fetch_locked(db, req_id)
    if req.employee_id != me.id:
        raise AppError(
            "forbidden",
            "You can request cancellation only for your own leave request.",
            403,
        )
    if req.status == LeaveStatus.cancellation_requested:
        raise AppError(
            "conflict",
            "This leave already has a cancellation request awaiting review.",
            409,
        )
    if req.status != LeaveStatus.approved:
        raise AppError(
            "conflict",
            "Only approved leave requests can have cancellation requested.",
            409,
        )
    # end_date, not start_date: an employee who came back to work partway
    # through an approved absence still needs to withdraw the remainder.
    if req.end_date < _today():
        raise AppError("validation_error", "Past leave requests cannot be cancelled.", 422)

    req.status = LeaveStatus.cancellation_requested
    req.updated_by = actor.id
    db.add(req)
    # The leave is still active until a manager decides, so nothing is reversed
    # here - the days stay marked and the balance stays deducted.
    _audit_decision(
        db, actor=actor, action=AuditAction.LEAVE_CANCELLATION_REQUEST, req=req
    )
    db.commit()
    db.refresh(req)
    _notify_routed_approver(
        db, me, req, "leave_cancellation_requested",
        f"{me.full_name} requested leave cancellation",
        f"{me.employee_code} - {me.full_name} requested cancellation of approved "
        f"leave for {_period(req)}.",
        queue="cancellation",
    )
    return req


def approve_leave_cancellation(
    db: Session, actor: User, req_id: uuid.UUID
) -> LeaveRequest:
    """cancellation_requested -> cancelled. The manager's approval cancels the
    leave outright; there is no second step for the employee.

    PHASE 10: this now REVERSES what the approval did - the leave days come off
    the calendar and the deducted balance goes back. Only days that still look
    exactly like an approval wrote them are removed, so a day the PM has since
    re-decided keeps that decision and is not refunded (see effects.py).
    """
    req = _fetch_locked(db, req_id)
    _assert_can_review(db, actor, req)
    if req.status != LeaveStatus.cancellation_requested:
        raise AppError(
            "conflict", "This cancellation request has already been processed.", 409
        )

    req.status = LeaveStatus.cancelled
    req.updated_by = actor.id
    db.add(req)

    effect = reverse_leave_approved(db, actor, req)
    # PHASE 3F: this is the one leave transition that ends an absence, so it is
    # the one that takes back the automatic leave reports written for it. AFTER
    # `reverse_leave_approved` and BEFORE the commit, so reconciliation reads the
    # `cancelled` status and the removed attendance rows, and so the cancellation
    # and its reconciliation land in one transaction or neither does.
    #
    # Requesting the withdrawal does NOT come here, and rejecting one returns the
    # row to `approved` - both leave the absence standing, so both leave the
    # reports locked. See `auto_reports.ACTIVE_LEAVE_STATUSES`.
    _reconcile_auto_leave_reports(db, req)
    _audit_decision(
        db,
        actor=actor,
        action=AuditAction.LEAVE_CANCELLATION_APPROVE,
        req=req,
        effect=effect,
    )
    db.commit()
    db.refresh(req)
    _notify_employee(
        db, req.employee_id, "leave_cancellation_approved",
        "Your leave cancellation was approved",
        f"Your leave cancellation request for {_period(req)} was approved."
        + _restored_sentence(effect),
        req.id,
        leave_request_path(req, view="my"),
    )
    return req


def reject_leave_cancellation(
    db: Session, actor: User, req_id: uuid.UUID
) -> LeaveRequest:
    """cancellation_requested -> approved. The original approval is untouched:
    manager_id and manager_comment still record who granted the leave."""
    req = _fetch_locked(db, req_id)
    _assert_can_review(db, actor, req)
    if req.status != LeaveStatus.cancellation_requested:
        raise AppError(
            "conflict", "This cancellation request has already been processed.", 409
        )

    req.status = LeaveStatus.approved
    req.updated_by = actor.id
    db.add(req)
    # The leave stands, so its days stay marked and its balance stays deducted -
    # nothing to apply and nothing to reverse.
    _audit_decision(
        db, actor=actor, action=AuditAction.LEAVE_CANCELLATION_REJECT, req=req
    )
    db.commit()
    db.refresh(req)
    _notify_employee(
        db, req.employee_id, "leave_cancellation_rejected",
        "Your leave cancellation was rejected",
        f"Your leave cancellation request for {_period(req)} was rejected. "
        "The approved leave remains active.",
        req.id,
        leave_request_path(req, view="my"),
    )
    return req


# ---------- attendance summary (cancellation-queue decision support) -------

# One word per leave request, in priority order when a range mixes statuses.
_ATTENDANCE_SUMMARY_NONE = "none"


def attendance_summaries(
    db: Session, actor: User, data: AttendanceSummaryRequest
) -> list[LeaveAttendanceSummaryOut]:
    """Read-only: what attendance already exists across each leave request's
    dates, summarised to a single word for the cancellation queue.

    Two bulk queries for the whole displayed page (no per-row querying), and it
    runs outside the cancellation transaction â€” it never writes.
    """
    _assert_can_review(db, actor)
    if not data.leave_request_ids:
        return []

    reqs = (
        db.execute(
            select(LeaveRequest).where(LeaveRequest.id.in_(data.leave_request_ids))
        )
        .scalars()
        .all()
    )
    if not reqs:
        return []

    # Bound the scan to the widest window across all displayed rows, then bucket
    # in Python â€” one query rather than one per leave request.
    lo = min(r.start_date for r in reqs)
    hi = max(r.end_date for r in reqs)
    rows = db.execute(
        select(
            AttendanceRecord.employee_id,
            AttendanceRecord.attendance_date,
            AttendanceRecord.status,
        ).where(
            AttendanceRecord.employee_id.in_({r.employee_id for r in reqs}),
            AttendanceRecord.attendance_date >= lo,
            AttendanceRecord.attendance_date <= hi,
        )
    ).all()
    by_employee: dict[uuid.UUID, list] = {}
    for row in rows:
        by_employee.setdefault(row.employee_id, []).append(row)

    items: list[LeaveAttendanceSummaryOut] = []
    for r in reqs:
        covered = [
            row
            for row in by_employee.get(r.employee_id, ())
            if r.start_date <= row.attendance_date <= r.end_date
        ]
        statuses = {row.status for row in covered}
        days = len(covered)
        if not statuses:
            summary = _ATTENDANCE_SUMMARY_NONE
        elif len(statuses) > 1:
            summary = "mixed"
        else:
            summary = next(iter(statuses)).value
        items.append(
            LeaveAttendanceSummaryOut(
                leave_request_id=r.id, summary=summary, days_recorded=days
            )
        )
    return items


# ---------- manager / admin review ----------------------------------------

def approve_leave_request(
    db: Session, actor: User, req_id: uuid.UUID, data: LeaveReviewBody
) -> LeaveRequest:
    # Locked before the status check so an employee cancelling the same request
    # concurrently cannot slip in between the read and the write.
    req = _fetch_locked(db, req_id)
    _assert_can_review(db, actor, req)
    if req.status != LeaveStatus.pending:
        raise AppError("validation_error", "Only pending requests can be approved.", 422)

    # Guard against approving leave for days the employee was actually present
    # (e.g. a request filed before attendance was marked). Reject it instead.
    worked = _worked_attendance_dates(db, req.employee_id, req.start_date, req.end_date)
    if worked:
        raise AppError(
            "validation_error",
            f"This employee is marked present on {_format_dates(worked)}; their leave "
            "can't be approved. Reject the request instead.",
            422,
        )

    # Sized against exactly the days that will really be marked - working days
    # only, minus any day that already carries an official decision - so the
    # check and the deduction can never disagree about what this request costs.
    to_mark, _skipped = plan_leave_days(db, req)

    # The same refusal on biometric grounds, against that same day list.
    # Re-checked here and not only at create: punches sync in from the office
    # connector on their own schedule, so a request filed on Monday morning can
    # still be in the queue when Monday's own punches arrive. Approving then
    # would write Leave over a day the device had, by that point, settled as
    # worked.
    _assert_approvable_against_biometric(db, req.employee_id, to_mark)

    # THE BALANCE DOES NOT GATE THE APPROVAL.
    #
    # There used to be an eligibility guard here that refused any request costing
    # more days than `ledger.spendable_on` reported, telling the reviewer to
    # reject it or have it refiled as unpaid. That is not the business rule: an
    # approver decides whether the absence is warranted, not whether it is
    # currently funded, and a genuine leave does not stop being genuine because
    # the pool is empty. A short balance now approves and goes NEGATIVE.
    #
    # Nothing needs to be added to make that work, which is why this is a
    # deletion and not a replacement. The ledger already carries a deficit
    # faithfully and already reconciles it:
    #
    #   consumption   is the `leave` attendance rows `apply_leave_approved`
    #                 writes below - marking the day IS the deduction, so an
    #                 approval that overdraws simply produces a closing balance
    #                 below zero (`ledger.py`: "NEGATIVES ARE REAL. Nothing is
    #                 clamped.")
    #   carry-forward is `carry_in(M) = closing(M-1)`, unclamped, so the deficit
    #                 survives into the next month
    #   reconciliation is `available(M) = carry_in + allocation + adjustment`, so
    #                 the next month's accrual offsets the deficit on its own:
    #                 -2 then +1/month reads -1, then 0.
    #
    # The guards that DO still gate an approval are untouched and sit above this
    # comment: a day the employee is recorded present for, and a day the
    # biometric device has settled as worked.
    reviewer = _current_employee(db, actor)
    req.status = LeaveStatus.approved
    req.manager_id = reviewer.id if reviewer else None
    req.manager_comment = data.comment
    req.updated_by = actor.id
    db.add(req)

    # Marks the calendar and moves the balance in THIS transaction, so the
    # request can never be left approved with its days unmarked.
    effect = apply_leave_approved(db, actor, req)
    _audit_decision(
        db,
        actor=actor,
        action=AuditAction.LEAVE_REQUEST_APPROVE,
        req=req,
        comment=data.comment,
        effect=effect,
    )
    db.commit()
    db.refresh(req)
    _notify_employee(
        db, req.employee_id, "leave_approved",
        "Your leave request was approved",
        f"Your leave request ({req.start_date} to {req.end_date}) has been approved."
        + _effect_sentence(effect, req),
        req.id,
        leave_request_path(req, view="my"),
    )
    # Tell the employee by email too. Placed AFTER the commit and after the bell
    # on purpose: the decision is already durable and the notification already
    # delivered, so nothing this call does - including an unreachable broker or
    # an employee with no work email - can cost either of them. It never raises.
    #
    # Attached to this function rather than to `_push`/`_notify_employee`, which
    # the cancellation events share: only an approval and a rejection email.
    leave_email.send_approval_email(db, req, reviewer)
    return req


def reject_leave_request(
    db: Session, actor: User, req_id: uuid.UUID, data: LeaveReviewBody
) -> LeaveRequest:
    req = _fetch_locked(db, req_id)
    _assert_can_review(db, actor, req)
    if req.status != LeaveStatus.pending:
        raise AppError("validation_error", "Only pending requests can be rejected.", 422)

    reviewer = _current_employee(db, actor)
    req.status = LeaveStatus.rejected
    req.manager_id = reviewer.id if reviewer else None
    req.manager_comment = data.comment
    req.updated_by = actor.id
    db.add(req)
    # No effect is applied: a rejected request marks no day and moves no balance.
    _audit_decision(
        db,
        actor=actor,
        action=AuditAction.LEAVE_REQUEST_REJECT,
        req=req,
        comment=data.comment,
    )
    db.commit()
    db.refresh(req)
    _notify_employee(
        db, req.employee_id, "leave_rejected",
        "Your leave request was rejected",
        f"Your leave request ({req.start_date} to {req.end_date}) was not approved."
        + (f" Note: {data.comment}" if data.comment else ""),
        req.id,
        leave_request_path(req, view="my"),
    )
    # See the note in `approve_leave_request`: after the commit, after the bell,
    # never raises, and reached from this function alone.
    leave_email.send_rejection_email(db, req, reviewer)
    return req


# ---------- deliverable impact (decision support) --------------------------

def deliverable_impacts(
    db: Session, actor: User, leave_request_ids: list[uuid.UUID]
) -> list[LeaveDeliverableImpactOut]:
    """For the given leave requests, find Planned deliverables whose target
    date falls within Â±2 days of the requested leave, on projects the
    requesting employee is assigned to.

    Informational only â€” never blocks approval. Computed in a handful of bulk
    queries for the whole displayed page (no per-row querying).
    """
    from app.modules.project_deliverables.models import (
        DeliverableStatus,
        ProjectDeliverable,
    )
    from app.modules.projects.models import Project, ProjectMember

    if actor.role != UserRole.project_manager:
        raise AppError(
            "forbidden", "Only project managers can review deliverable impact.", 403
        )
    if not leave_request_ids:
        return []

    # A cancelled request is no longer an absence, so it can no longer clash
    # with a deliverable â€” drop it before any conflict work is done.
    reqs = (
        db.execute(
            select(LeaveRequest).where(
                LeaveRequest.id.in_(leave_request_ids),
                LeaveRequest.status != LeaveStatus.cancelled,
            )
        )
        .scalars()
        .all()
    )
    if not reqs:
        return []

    employee_ids = {r.employee_id for r in reqs}

    # employee â†’ set of project ids they belong to
    member_rows = db.execute(
        select(ProjectMember.employee_id, ProjectMember.project_id).where(
            ProjectMember.employee_id.in_(employee_ids)
        )
    ).all()
    projects_by_emp: dict[uuid.UUID, set[uuid.UUID]] = {}
    project_ids: set[uuid.UUID] = set()
    for emp_id, proj_id in member_rows:
        projects_by_emp.setdefault(emp_id, set()).add(proj_id)
        project_ids.add(proj_id)
    if not project_ids:
        return []

    # Bound the deliverable scan to the widest possible impact window across
    # all displayed requests, so we never scan the whole deliverables table.
    win_lo = min(r.start_date for r in reqs) - DELIVERABLE_IMPACT_WINDOW
    win_hi = max(r.end_date for r in reqs) + DELIVERABLE_IMPACT_WINDOW

    deliv_rows = db.execute(
        select(
            ProjectDeliverable.id.label("deliverable_id"),
            ProjectDeliverable.project_id.label("project_id"),
            ProjectDeliverable.name.label("deliverable_name"),
            ProjectDeliverable.target_date.label("target_date"),
            Project.name.label("project_name"),
            Project.code.label("project_code"),
        )
        .join(Project, Project.id == ProjectDeliverable.project_id)
        .where(
            ProjectDeliverable.project_id.in_(project_ids),
            ProjectDeliverable.status == DeliverableStatus.planned,
            ProjectDeliverable.target_date.is_not(None),
            ProjectDeliverable.target_date >= win_lo,
            ProjectDeliverable.target_date <= win_hi,
            Project.deleted_at.is_(None),
        )
    ).all()
    delivs_by_project: dict[uuid.UUID, list] = {}
    for d in deliv_rows:
        delivs_by_project.setdefault(d.project_id, []).append(d)

    emp_names = {
        row.id: f"{row.first_name} {row.last_name}".strip()
        for row in db.execute(
            select(Employee.id, Employee.first_name, Employee.last_name).where(
                Employee.id.in_(employee_ids)
            )
        ).all()
    }

    items: list[LeaveDeliverableImpactOut] = []
    for r in reqs:
        # Leave [start, end] conflicts with deliverable date D when the leave
        # overlaps [D-2, D+2], i.e. D in [start-2, end+2].
        lo = r.start_date - DELIVERABLE_IMPACT_WINDOW
        hi = r.end_date + DELIVERABLE_IMPACT_WINDOW
        seen: set[uuid.UUID] = set()
        conflicts: list[DeliverableConflictOut] = []
        for proj_id in projects_by_emp.get(r.employee_id, ()):
            for d in delivs_by_project.get(proj_id, ()):
                if d.deliverable_id in seen or not (lo <= d.target_date <= hi):
                    continue
                seen.add(d.deliverable_id)
                conflicts.append(
                    DeliverableConflictOut(
                        deliverable_id=d.deliverable_id,
                        deliverable_name=d.deliverable_name,
                        project_id=d.project_id,
                        project_name=d.project_name,
                        project_code=d.project_code,
                        status=DeliverableStatus.planned.value,
                        target_date=d.target_date,
                        employee_id=r.employee_id,
                        employee_name=emp_names.get(r.employee_id),
                    )
                )
        if conflicts:
            conflicts.sort(key=lambda c: c.target_date or date.max)
            items.append(
                LeaveDeliverableImpactOut(leave_request_id=r.id, conflicts=conflicts)
            )
    return items

