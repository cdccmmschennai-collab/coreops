"""Permission Request service: RBAC-scoped reads + employee writes + PM review.

RBAC (identical to leave, deliberately - a permission is a smaller absence, not a
different kind of thing):
  project_manager  list all, approve/reject/cancel any - but never their own
  employee         list own, submit own, cancel own

Workflow (four states):
  pending  -> approved   (PM, and only if the month's balance covers it)
  pending  -> rejected   (PM, comment optional)
  pending  -> cancelled  (author, or a PM)
  approved -> cancelled  (author while the date is still ahead, or a PM) - the
                         hours come back

WHERE THE BALANCE LIVES
=======================
Nowhere. It is derived in `balance.py` from these rows: 4h a month minus that
month's approved hours. Nothing in this file writes a counter, which is why a
pending request cannot consume, a rejection cannot consume, and a cancellation
restores exactly what it took and cannot restore twice.

HOW A DECISION IS MADE SAFELY
=============================
Every status change locks first and validates second, the same discipline
`leave/service.py` uses - but the lock is wider. `balance.lock_month` takes
`FOR UPDATE` over ALL of the employee's requests in that month before the total
is summed, because the race that matters is not two writers on one row: it is two
DIFFERENT pending requests being approved at the same instant, each reading the
same remaining hours. Locking the month makes them queue, so the second one sees
the first one's approval and is refused.

ATTENDANCE IS NOT TOUCHED
=========================
Nothing here reads or writes `attendance_records`, `biometric_punches` or leave.
An approved permission leaves the day exactly as it was - `present` stays
`present` - and the hours sit beside it, joinable by (employee_id, date). That
join is what Phase 12 will render as "Present | 1hr - 7h 06m". Phase 11 only
guarantees the fact exists and is correct.
"""
import uuid
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import authz
from app.modules.audit.constants import AuditAction, EntityType
from app.modules.audit.service import record_audit
from app.modules.calendar.working_days import (
    is_working_day,
    load_calendar_overrides,
)
from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.leave.routing import resolve_routed_project
from app.modules.permissions.balance import (
    ALLOWED_DURATIONS,
    MONTHLY_ALLOWANCE_HOURS,
    PermissionBalance,
    balance_for,
    format_hours,
    hours_word,
    lock_month,
    month_bounds,
    month_has_closed,
)
from app.modules.permissions.models import PermissionRequest, PermissionStatus
from app.modules.permissions.schemas import (
    PermissionBalanceOut,
    PermissionHistoryOut,
    PermissionRequestBalanceOut,
    PermissionRequestCreate,
    PermissionRequestDetailOut,
    PermissionRequestOut,
    PermissionReviewBody,
)
from app.modules.users.models import User, UserRole
from app.shared.errors import AppError

# CoreOps runs on one business calendar. "Which month is now" and "has this date
# passed" must be judged on the Chennai business day: at 00:30 IST on 1 September
# the server's UTC date is still 31 August, which would put a September request in
# August's allowance. Same constant and same reason as `leave/service.py`.
BUSINESS_TZ = ZoneInfo("Asia/Kolkata")

# Statuses that still hold a live claim on a date, so a second request for the
# same day must be refused. `pending` counts here even though it consumes no
# balance - two live asks for one day are a duplicate, not two permissions.
_ACTIVE_STATUSES = (PermissionStatus.pending, PermissionStatus.approved)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return datetime.now(BUSINESS_TZ).date()


def _long_date(value: date) -> str:
    # Built from .day rather than %-d/%#d, which is platform-specific.
    return f"{value.day} {value:%B %Y}"


def _short_date(value: date) -> str:
    """`17 Aug 2026` - the form the notification messages use."""
    return f"{value.day:02d} {value:%b %Y}"


def _month_name(value: date) -> str:
    return f"{value:%B %Y}"


def _detail_url(req_id: uuid.UUID) -> str:
    """Where a notification about a permission should land: its detail page,
    which is also where a project manager's Approve/Reject live."""
    return f"/attendance/permission/{req_id}"


# ---------- notifications ---------------------------------------------------

def _push(db: Session, *, actor: User, user_id: uuid.UUID, type_: str, title: str,
          message: str, entity_id: uuid.UUID | None = None,
          target_url: str | None = None) -> None:
    """Best-effort notification; a delivery failure must never roll back the
    decision the caller already committed.

    NOBODY IS NOTIFIED OF THEIR OWN ACTION. As the code stands this is a backstop
    rather than a live path: every permission notification crosses parties by
    construction - self-review is refused outright, a cancellation is routed to
    whichever side did NOT perform it, and the `employees_no_self_manager` check
    constraint stops an employee being their own manager, which is the only way
    the manager route could point back at the actor.

    It is kept because all three of those are separate decisions made elsewhere,
    and any of them changing would silently start telling people about things they
    just did themselves. Asserting it here costs one comparison.
    """
    if actor.id == user_id:
        return
    try:
        from app.modules.notifications.service import create_notification
        create_notification(db, user_id=user_id, type_=type_, title=title, message=message,
                            entity_type="permission_request", entity_id=entity_id,
                            target_url=target_url)
        db.commit()
    except Exception:
        db.rollback()


def _notify_manager(db: Session, actor: User, employee: Employee, type_: str,
                    title: str, message: str, entity_id: uuid.UUID | None = None,
                    target_url: str | None = None) -> None:
    if employee.manager_id is None:
        return
    mgr = db.get(Employee, employee.manager_id)
    if mgr is None or mgr.user_id is None:
        return
    _push(db, actor=actor, user_id=mgr.user_id, type_=type_, title=title,
          message=message, entity_id=entity_id, target_url=target_url)


def _notify_employee(db: Session, actor: User, employee_id: uuid.UUID, type_: str,
                     title: str, message: str, entity_id: uuid.UUID | None = None,
                     target_url: str | None = None) -> None:
    emp = db.get(Employee, employee_id)
    if emp is None or emp.user_id is None:
        return
    _push(db, actor=actor, user_id=emp.user_id, type_=type_, title=title,
          message=message, entity_id=entity_id, target_url=target_url)


def _reporting_pm_employee(db: Session, employee: Employee) -> Employee | None:
    """The employee record of the requester's reporting PM, or None.

    `Employee.reporting_pm_id` is a **users.id**, not an employees.id, so it is
    resolved back to the PM's employee row - the same lookup
    `leave/recipients.py::_reporting_pm_employee` performs for Leave. Kept as a
    small local copy rather than a cross-module import: this is a four-line
    query, not shared logic worth coupling the two modules over.
    """
    if employee.reporting_pm_id is None:
        return None
    return db.execute(
        select(Employee)
        .where(
            Employee.user_id == employee.reporting_pm_id,
            Employee.deleted_at.is_(None),
        )
        .limit(1)
    ).scalars().first()


def _routed_recipient(db: Session, employee: Employee, req: PermissionRequest) -> Employee | None:
    """Who the in-app channel notifies about this request: the routed project's
    CURRENT Head if reachable (a linked user_id), else the requester's
    reporting PM - the SAME fallback order `leave/recipients.py` uses, and
    deliberately NOT `employee.manager_id` (the line manager is not an
    authorized reviewer here any more than for Leave).
    """
    if req.routed_project_id is not None:
        head_id = authz.project_head_employee_id(db, req.routed_project_id)
        if head_id is not None and head_id != employee.id:
            head = db.get(Employee, head_id)
            if head is not None and head.user_id is not None:
                return head
    pm = _reporting_pm_employee(db, employee)
    if pm is not None and pm.id != employee.id and pm.user_id is not None:
        return pm
    return None


def _notify_routed_approver(db: Session, actor: User, employee: Employee, req: PermissionRequest,
                            type_: str, title: str, message: str) -> None:
    recipient = _routed_recipient(db, employee, req)
    if recipient is None:
        return
    _push(db, actor=actor, user_id=recipient.user_id, type_=type_, title=title,
          message=message, entity_id=req.id, target_url=_detail_url(req.id))


# ---------- audit -----------------------------------------------------------

def _audit(
    db: Session,
    *,
    actor: User,
    action: str,
    req: PermissionRequest,
    comment: str | None = None,
    before: PermissionBalance | None = None,
    after: PermissionBalance | None = None,
) -> None:
    """Record one permission event through the SAME `record_audit` every other
    CoreOps module uses. FLUSHES, never commits.

    The balance is derived, so these rows are the only written record of the
    movement: `remaining_before` / `remaining_after` are what makes "who spent
    this employee's August hours" answerable after the fact.
    """
    details: dict = {
        "permission_request_id": str(req.id),
        "employee_id": str(req.employee_id),
        "permission_date": req.permission_date.isoformat(),
        "duration_hours": req.duration_hours,
        "status": req.status.value,
        "month": req.permission_date.strftime("%Y-%m"),
    }
    if comment and comment.strip():
        details["comment"] = comment.strip()
    if before is not None:
        details["remaining_before"] = before.remaining_hours
    if after is not None:
        details["remaining_after"] = after.remaining_hours
        details["allowance_hours"] = after.allowance_hours

    record_audit(
        db,
        action=action,
        actor=actor,
        entity_type=EntityType.PERMISSION_REQUEST,
        entity_id=req.id,
        details=details,
    )


# ---------- scope / authorisation ------------------------------------------

def _apply_scope(db: Session, actor: User, stmt):
    if actor.role == UserRole.project_manager:
        return stmt, True
    me = _current_employee(db, actor)
    if me is None:
        return stmt, False
    return stmt.where(PermissionRequest.employee_id == me.id), True


def _assert_can_read(db: Session, actor: User, req: PermissionRequest) -> None:
    if actor.role == UserRole.project_manager:
        return
    if req.routed_project_id is not None and authz.can_review_report(
        db, actor, {req.routed_project_id}
    ):
        return
    me = _current_employee(db, actor)
    if me is None or req.employee_id != me.id:
        raise AppError("forbidden", "You can only view your own permission requests.", 403)


def _assert_can_review(db: Session, actor: User, req: PermissionRequest) -> None:
    """Who may rule on a permission request - enforced here, on every decision
    path, regardless of what the frontend chose to render.

    PM (any request) or the CURRENT Head of the request's routed project may
    review (Phase 4B) - `authz.can_review_report` is the same PM-or-Head rule
    Leave and Work Reports already use, so this stays a one-line delegation
    rather than a second copy of it.

    NOBODY APPROVES THEIR OWN PERMISSION, project manager or Head included: both
    are employees too and file their own requests, so without the second check
    either could grant themselves hours out of their own allowance.
    """
    project_ids = {req.routed_project_id} if req.routed_project_id is not None else set()
    if not authz.can_review_report(db, actor, project_ids):
        raise AppError(
            "forbidden",
            "Only a project manager or this request's assigned Project Head can "
            "review it.",
            403,
        )
    me = _current_employee(db, actor)
    if me is not None and req.employee_id == me.id:
        raise AppError(
            "forbidden",
            "You can't review your own permission request - another reviewer "
            "has to decide it.",
            403,
        )


def _author_employee(db: Session, actor: User) -> Employee:
    me = _current_employee(db, actor)
    if me is None:
        raise AppError(
            "validation_error",
            "You need an employee profile to submit a permission request.",
            422,
        )
    return me


# ---------- validation -----------------------------------------------------

def _assert_working_day(db: Session, value: date) -> None:
    """A permission is time off INSIDE a working day, so a non-working day cannot
    have one - there are no hours there to be released from.

    Resolved by `calendar/working_days.py`, CoreOps' existing and already-tested
    answer to "is the office open", so a declared working-Saturday override is
    honoured and a public holiday is refused.
    """
    non_working, working_overrides = load_calendar_overrides(db, value, value)
    if not is_working_day(
        value, non_working=non_working, working_overrides=working_overrides
    ):
        raise AppError(
            "validation_error",
            f"{_long_date(value)} is not a working day, so it can't have a "
            "permission.",
            422,
        )


def _assert_month_open(value: date) -> None:
    """Refuse a NEW request for a month that has already ended.

    A permission allowance is monthly and does not carry forward, so once August
    is over there is no August allowance left to draw on - filing against it
    would be asking to spend hours that ceased to exist at midnight on the 31st.

    Only CREATION is blocked. August stays fully readable: its history, its
    figures and its already-approved requests are unchanged, and a manager can
    still approve, reject or cancel a request that was filed while the month was
    open - correcting a past decision is not the same as making a new one.

    Enforced here rather than by hiding a button, so a direct API call is refused
    too. A FUTURE month is deliberately untouched: filing ahead has always
    worked and this phase introduces no future-month policy.
    """
    today = _today()
    if not month_has_closed(value, today):
        return
    raise AppError(
        "validation_error",
        f"{_month_name(value)} has ended, so a new permission request can't be "
        f"created for {_long_date(value)}. Permission hours don't carry forward - "
        f"you can still view {_month_name(value)}, and request permission for "
        f"{_month_name(today)}.",
        422,
    )


def _assert_no_active_request(
    db: Session,
    employee_id: uuid.UUID,
    value: date,
    *,
    exclude_id: uuid.UUID | None = None,
) -> None:
    """One live permission per day. Somebody who needs two hours off asks for a
    2h permission, not two 1h ones - otherwise each approval would charge the
    allowance separately for what is one absence."""
    stmt = select(PermissionRequest).where(
        PermissionRequest.employee_id == employee_id,
        PermissionRequest.permission_date == value,
        PermissionRequest.status.in_(_ACTIVE_STATUSES),
    )
    if exclude_id is not None:
        stmt = stmt.where(PermissionRequest.id != exclude_id)
    clash = db.execute(stmt.limit(1)).scalar_one_or_none()
    if clash is None:
        return
    raise AppError(
        "validation_error",
        f"You already have a {clash.status.value} permission request for "
        f"{_long_date(value)}.",
        422,
    )


def _fetch(db: Session, req_id: uuid.UUID) -> PermissionRequest:
    req = db.get(PermissionRequest, req_id)
    if req is None:
        raise AppError("not_found", "Permission request not found.", 404)
    return req


def _fetch_locked(db: Session, req_id: uuid.UUID) -> PermissionRequest:
    """Load the request with the whole month locked around it.

    The month lock is taken FIRST and in `id` order (see `balance.lock_month`),
    then the row is re-read inside that lock. Taking the target row first and the
    month second would let two writers on two different rows of the same month
    grab them in opposite orders and deadlock.

    Callers must therefore call this BEFORE checking status, never after.
    """
    req = _fetch(db, req_id)
    lock_month(db, req.employee_id, req.permission_date)
    db.refresh(req)
    return req


# ---------- reads ----------------------------------------------------------

def list_permission_requests(
    db: Session,
    actor: User,
    *,
    employee_id: uuid.UUID | None,
    status: PermissionStatus | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    offset: int,
    order_by: str = "created_at",
) -> tuple[list[PermissionRequest], int]:
    """The one scoped, filtered read every permission list is built from.

    `order_by` exists because the two callers want genuinely different orders and
    neither should grow its own query: the review QUEUE is a work list, so oldest
    ask first is wrong and newest-submitted first is what a manager expects, while
    monthly HISTORY is a calendar, so it reads by the day the absence falls on.
    """
    stmt = select(PermissionRequest)
    stmt, allowed = _apply_scope(db, actor, stmt)
    if not allowed:
        return [], 0

    if employee_id is not None:
        stmt = stmt.where(PermissionRequest.employee_id == employee_id)
    if status is not None:
        stmt = stmt.where(PermissionRequest.status == status)
    if date_from is not None:
        stmt = stmt.where(PermissionRequest.permission_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(PermissionRequest.permission_date <= date_to)

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    if order_by == "permission_date":
        # created_at breaks the tie so two same-day requests have a stable order.
        order = (PermissionRequest.permission_date.desc(), PermissionRequest.created_at.desc())
    else:
        order = (PermissionRequest.created_at.desc(),)
    rows = (
        db.execute(stmt.order_by(*order).limit(limit).offset(offset)).scalars().all()
    )
    return list(rows), total


def get_permission_request(
    db: Session, actor: User, req_id: uuid.UUID
) -> PermissionRequest:
    req = _fetch(db, req_id)
    _assert_can_read(db, actor, req)
    return req


# ---------- detail ---------------------------------------------------------

def _employee_names(
    db: Session, employee_ids: set[uuid.UUID]
) -> dict[uuid.UUID, Employee]:
    ids = {i for i in employee_ids if i is not None}
    if not ids:
        return {}
    rows = db.execute(select(Employee).where(Employee.id.in_(ids))).scalars().all()
    return {e.id: e for e in rows}


def _request_balance(
    db: Session, req: PermissionRequest
) -> PermissionRequestBalanceOut:
    """This request's place in its month, stated without pretending.

    Only an approved request has consumed anything, so `consumed_by_request` is 0
    for pending, rejected and cancelled - a cancelled request in particular must
    not read as though its hours are still spent, because they are not: it has
    stopped contributing to the month's approved total.
    """
    balance = balance_for(db, req.employee_id, req.permission_date)
    consumed = req.duration_hours if req.status == PermissionStatus.approved else 0
    return PermissionRequestBalanceOut(
        month=balance.month,
        allowance_hours=balance.allowance_hours,
        approved_hours=balance.approved_hours,
        remaining_hours=balance.remaining_hours,
        consumed_by_request=consumed,
        # What the month would have if this request did not exist. For a request
        # that consumed nothing, that is simply the current remaining figure.
        remaining_before_request=balance.remaining_hours + consumed,
        # Only a pending request still has an outcome to forecast.
        remaining_if_approved=(
            max(0, balance.remaining_hours - req.duration_hours)
            if req.status == PermissionStatus.pending
            else None
        ),
    )


def get_permission_detail(
    db: Session, actor: User, req_id: uuid.UUID
) -> PermissionRequestDetailOut:
    """One request with its names and its balance context, in a single call.

    Authorisation is the SAME `_assert_can_read` the plain read uses - an employee
    sees only their own, a project manager sees any - so the detail page cannot
    become a way around the list's scoping.
    """
    req = _fetch(db, req_id)
    _assert_can_read(db, actor, req)

    people = _employee_names(db, {req.employee_id, req.manager_id})
    employee = people.get(req.employee_id)
    reviewer = people.get(req.manager_id) if req.manager_id else None

    return PermissionRequestDetailOut(
        **PermissionRequestOut.model_validate(req).model_dump(),
        employee_name=employee.full_name if employee else None,
        employee_code=employee.employee_code if employee else None,
        reviewer_name=reviewer.full_name if reviewer else None,
        balance=_request_balance(db, req),
    )


# ---------- monthly history ------------------------------------------------

def _history_subject(
    db: Session, actor: User, employee_id: uuid.UUID | None
) -> Employee:
    """Whose history is being read.

    Defaults to the caller. An explicit `employee_id` is honoured only for a
    project manager, or for an employee naming themselves - otherwise an employee
    could read a colleague's month by editing a query parameter.
    """
    me = _author_employee(db, actor)
    if employee_id is None or employee_id == me.id:
        return me
    if actor.role != UserRole.project_manager:
        raise AppError(
            "forbidden", "You can only view your own permission history.", 403
        )
    subject = db.get(Employee, employee_id)
    if subject is None:
        raise AppError("not_found", "Employee not found.", 404)
    return subject


def permission_history(
    db: Session,
    actor: User,
    *,
    employee_id: uuid.UUID | None,
    month_of: date | None,
    limit: int,
    offset: int,
) -> PermissionHistoryOut:
    """One calendar month of history, plus that month's balance.

    The month is bounded by `balance.month_bounds` and filtered on
    `permission_date` - the day of the absence - NEVER on `created_at`. A request
    filed on 1 September for 31 August belongs to August in both the table and the
    figure above it, because it is the same month in both cases: they come from
    the same bounds computed once, here.
    """
    subject = _history_subject(db, actor, employee_id)
    today = _today()
    month_ref = month_of or today
    start, end = month_bounds(month_ref)

    rows, total = list_permission_requests(
        db,
        actor,
        employee_id=subject.id,
        status=None,
        date_from=start,
        date_to=end,
        limit=limit,
        offset=offset,
        order_by="permission_date",
    )
    balance = balance_for(db, subject.id, month_ref, today)
    return PermissionHistoryOut(
        employee_id=subject.id,
        month=start,
        balance=PermissionBalanceOut(
            employee_id=balance.employee_id,
            month=balance.month,
            allowance_hours=balance.allowance_hours,
            approved_hours=balance.approved_hours,
            remaining_hours=balance.remaining_hours,
            is_current_month=balance.is_current_month,
            requests_allowed=balance.requests_allowed,
        ),
        items=[PermissionRequestOut.model_validate(r) for r in rows],
        total=total,
    )


def my_balance(db: Session, actor: User, month_of: date | None = None) -> PermissionBalance:
    """The signed-in employee's own permission balance, current month by default.

    "Current" is the Chennai business month, so the KPI does not flip a day early
    for anyone reading it just after midnight IST.

    The returned balance also says whether that month can still be requested
    against, so the attendance page can show a historical month's figures without
    offering an action the backend would refuse.
    """
    me = _author_employee(db, actor)
    today = _today()
    return balance_for(db, me.id, month_of or today, today)


def employee_balance(
    db: Session, actor: User, employee_id: uuid.UUID, month_of: date | None = None
) -> PermissionBalance:
    """Any employee's balance - project managers only, for the review queue."""
    if actor.role != UserRole.project_manager:
        raise AppError(
            "forbidden", "Only project managers can read another employee's balance.", 403
        )
    today = _today()
    return balance_for(db, employee_id, month_of or today, today)


# ---------- employee writes ------------------------------------------------

def create_permission_request(
    db: Session, actor: User, data: PermissionRequestCreate
) -> PermissionRequest:
    """Submit a request. Status is `pending` and NOTHING is consumed.

    The balance is deliberately NOT checked here. A pending request holds no
    hours, so refusing to file one when the month is spent would be inventing a
    reservation the rest of the system does not have; the approval is where the
    allowance is enforced. The duration is validated (1h or 2h) by the schema, by
    the guard below, and by the DB check constraint.
    """
    me = _author_employee(db, actor)
    if data.duration_hours not in ALLOWED_DURATIONS:
        raise AppError(
            "validation_error", "A permission must be either 1 hour or 2 hours.", 422
        )
    # Checked before the working-day rule: "August is over" is a better answer
    # than "16 August was a Sunday" for somebody who has navigated back a month.
    _assert_month_open(data.permission_date)
    _assert_working_day(db, data.permission_date)
    _assert_no_active_request(db, me.id, data.permission_date)

    req = PermissionRequest(
        employee_id=me.id,
        permission_date=data.permission_date,
        duration_hours=data.duration_hours,
        reason=data.reason,
        status=PermissionStatus.pending,
        # Phase 4B: the same work-report-evidence resolver Leave uses, given the
        # permission date as the boundary. NULL when no single project can be
        # established, which falls back to the existing PM / reporting_pm_id
        # flow below via `_notify_routed_approver`.
        routed_project_id=resolve_routed_project(db, me.id, data.permission_date),
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(req)
    db.flush()
    _audit(db, actor=actor, action=AuditAction.PERMISSION_REQUEST_SUBMIT, req=req)
    db.commit()
    db.refresh(req)

    hours = req.duration_hours
    _notify_routed_approver(
        db, actor, me, req, "permission_submitted",
        f"{me.full_name} submitted a permission request",
        f"{me.full_name} requested {hours} {hours_word(hours)} of permission for "
        f"{_short_date(req.permission_date)}.",
    )
    return req


def cancel_permission_request(
    db: Session, actor: User, req_id: uuid.UUID
) -> PermissionRequest:
    """pending | approved -> cancelled.

    Cancelling an APPROVED permission gives the hours back, and gives them back
    exactly once: the balance is a sum over approved rows, so this row simply
    stops counting. A second attempt is refused by the status guard below, which
    is why "do not double-restore" needs no bookkeeping of its own.

    Who may do it: the author, and a project manager. The author is additionally
    held to a date that has not passed - a finished absence has nothing left to
    withdraw, and correcting the record after the fact is an attendance job.
    """
    req = _fetch_locked(db, req_id)
    me = _current_employee(db, actor)
    is_author = me is not None and req.employee_id == me.id
    is_manager = actor.role == UserRole.project_manager

    if not (is_author or is_manager):
        raise AppError(
            "forbidden", "You can only cancel your own permission requests.", 403
        )
    if req.status == PermissionStatus.cancelled:
        raise AppError("conflict", "This permission request is already cancelled.", 409)
    if req.status not in _ACTIVE_STATUSES:
        raise AppError(
            "conflict",
            f"A {req.status.value} permission request can't be cancelled.",
            409,
        )
    # A manager may still correct a past decision; the employee's own withdrawal
    # window closes when the day does.
    if is_author and not is_manager and req.permission_date < _today():
        raise AppError(
            "validation_error",
            "Past permission requests can't be cancelled.",
            422,
        )

    before = balance_for(db, req.employee_id, req.permission_date)
    restored = req.status == PermissionStatus.approved
    req.status = PermissionStatus.cancelled
    req.updated_by = actor.id
    db.add(req)
    db.flush()
    after = balance_for(db, req.employee_id, req.permission_date)

    _audit(
        db,
        actor=actor,
        action=AuditAction.PERMISSION_REQUEST_CANCEL,
        req=req,
        before=before,
        after=after,
    )
    db.commit()
    db.refresh(req)

    # Whoever did NOT do it is the one who needs telling, which is the same
    # convention leave cancellation follows. `_push` suppresses the actor anyway,
    # so an author who is also a project manager is never told by themselves.
    hours = req.duration_hours
    if is_author:
        # The manager owns the queue this request has just left.
        _notify_manager(
            db, actor, me, "permission_cancelled",
            f"{me.full_name} cancelled a permission request",
            f"{me.full_name} cancelled their {hours}-{hours_word(hours)} permission "
            f"request for {_short_date(req.permission_date)}."
            + (
                f" {format_hours(after.remaining_hours)} of permission remaining "
                f"for {_month_name(req.permission_date)}."
                if restored
                else ""
            ),
            req.id,
            _detail_url(req.id),
        )
    else:
        _notify_employee(
            db, actor, req.employee_id, "permission_cancelled",
            "Your permission request was cancelled",
            f"Your {hours}-{hours_word(hours)} permission request for "
            f"{_short_date(req.permission_date)} was cancelled."
            + (
                f" {format_hours(after.remaining_hours)} of permission remaining "
                f"for {_month_name(req.permission_date)}."
                if restored
                else ""
            ),
            req.id,
            _detail_url(req.id),
        )
    return req


# ---------- project-manager review ----------------------------------------

def approve_permission_request(
    db: Session, actor: User, req_id: uuid.UUID, data: PermissionReviewBody
) -> PermissionRequest:
    """pending -> approved, consuming the hours from that month's allowance.

    The month is locked before the balance is summed, so two approvals racing on
    the same employee's month cannot both read the same remaining figure - the
    second blocks, re-reads, and is refused if the first spent what it needed.
    That is the only thing standing between concurrent approvals and a negative
    allowance, since there is no stored counter for a constraint to protect.
    """
    req = _fetch_locked(db, req_id)
    _assert_can_review(db, actor, req)
    if req.status != PermissionStatus.pending:
        raise AppError(
            "validation_error", "Only pending requests can be approved.", 422
        )

    before = balance_for(db, req.employee_id, req.permission_date)
    if req.duration_hours > before.remaining_hours:
        raise AppError(
            "validation_error",
            f"Insufficient permission balance: {req.duration_hours} "
            f"{hours_word(req.duration_hours)} requested, "
            f"{format_hours(before.remaining_hours)} remaining of the "
            f"{format_hours(MONTHLY_ALLOWANCE_HOURS)} allowance for "
            f"{_month_name(req.permission_date)}. Reject the request instead.",
            422,
        )

    reviewer = _current_employee(db, actor)
    req.status = PermissionStatus.approved
    req.manager_id = reviewer.id if reviewer else None
    req.manager_comment = data.comment
    req.reviewed_at = _now()
    req.updated_by = actor.id
    db.add(req)
    db.flush()
    after = balance_for(db, req.employee_id, req.permission_date)

    _audit(
        db,
        actor=actor,
        action=AuditAction.PERMISSION_REQUEST_APPROVE,
        req=req,
        comment=data.comment,
        before=before,
        after=after,
    )
    db.commit()
    db.refresh(req)

    hours = req.duration_hours
    _notify_employee(
        db, actor, req.employee_id, "permission_approved",
        "Your permission request was approved",
        f"Your permission request for {_short_date(req.permission_date)} for "
        f"{hours} {hours_word(hours)} has been approved. "
        f"{format_hours(after.remaining_hours)} of permission remaining for "
        f"{_month_name(req.permission_date)}."
        + (f" Note: {data.comment.strip()}" if data.comment and data.comment.strip() else ""),
        req.id,
        _detail_url(req.id),
    )
    return req


def reject_permission_request(
    db: Session, actor: User, req_id: uuid.UUID, data: PermissionReviewBody
) -> PermissionRequest:
    """pending -> rejected. Consumes nothing: the balance sums approved rows only,
    so there is no deduction to skip and none to undo."""
    req = _fetch_locked(db, req_id)
    _assert_can_review(db, actor, req)
    if req.status != PermissionStatus.pending:
        raise AppError(
            "validation_error", "Only pending requests can be rejected.", 422
        )

    reviewer = _current_employee(db, actor)
    req.status = PermissionStatus.rejected
    req.manager_id = reviewer.id if reviewer else None
    req.manager_comment = data.comment
    req.reviewed_at = _now()
    req.updated_by = actor.id
    db.add(req)
    db.flush()

    _audit(
        db,
        actor=actor,
        action=AuditAction.PERMISSION_REQUEST_REJECT,
        req=req,
        comment=data.comment,
        after=balance_for(db, req.employee_id, req.permission_date),
    )
    db.commit()
    db.refresh(req)

    hours = req.duration_hours
    _notify_employee(
        db, actor, req.employee_id, "permission_rejected",
        "Your permission request was rejected",
        f"Your permission request for {_short_date(req.permission_date)} for "
        f"{hours} {hours_word(hours)} has been rejected."
        + (f" Note: {data.comment.strip()}" if data.comment and data.comment.strip() else ""),
        req.id,
        _detail_url(req.id),
    )
    return req
