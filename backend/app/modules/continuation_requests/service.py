"""ContinuationRequest service - Lump-sum Activity Continuation Approval
(Phase 2).

Employees request approval to continue an overdue lump-sum WorkItem; the
project's CURRENT Head (or, with no Head, the employee's line manager as a
notification fallback - mirrors leave/service.py exactly) reviews. Head/PM
authorization reuses app.core.authz verbatim; nothing here duplicates it.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import authz
from app.modules.activity_master.models import ActivityMaster
from app.modules.continuation_requests.models import ContinuationRequest, ContinuationRequestStatus
from app.modules.continuation_requests.schemas import ContinuationRequestCreate
from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.projects.models import Project
from app.modules.users.models import User, UserRole
from app.modules.work_reports.models import DailyWorkReport, WorkItem, WorkReportTask
from app.modules.work_reports.work_items import (
    count_work_days,
    lumpsum_allowance_exhausted,
)
from app.shared.errors import AppError

# The reviewer surface for this feature is its own top-level page, reached from
# the Homepage Shortcuts - deliberately NOT a tab under /attendance, and never
# merged with Leave. See the SDD ledger, decision D-1.
REVIEW_URL = "/lump-sum-activity"


# -- notification helpers (mirrors leave/service.py's _push/_notify_*) --------

def _push(db: Session, user_id: uuid.UUID, type_: str, title: str, message: str,
          entity_id: uuid.UUID | None = None, target_url: str | None = None) -> None:
    try:
        from app.modules.notifications.service import create_notification
        create_notification(
            db, user_id=user_id, type_=type_, title=title, message=message,
            entity_type="continuation_request", entity_id=entity_id, target_url=target_url,
        )
        db.commit()
    except Exception:
        db.rollback()


def _notify_reviewer(db: Session, employee: Employee, req: ContinuationRequest, sub_name: str) -> None:
    """Notify whoever must act: the CURRENT Head of req.project_id if one is
    assigned (and isn't the requester), else the employee's line manager -
    mirrors leave.service._notify_routed_approver's fallback exactly (spec:
    PM-fallback = line manager, not the project_managers assignment table).
    Resolved fresh, never off a frozen value."""
    target_url = f"{REVIEW_URL}?queue=pending&id={req.id}"
    head_id = authz.project_head_employee_id(db, req.project_id)
    if head_id is not None and head_id != employee.id:
        head = db.get(Employee, head_id)
        if head is not None and head.user_id is not None:
            _push(
                db, head.user_id, "continuation_requested",
                f"{employee.full_name} needs continuation approval",
                f"{employee.full_name} requested continuation approval for "
                f"'{sub_name}' beyond its allowed duration.",
                req.id, target_url,
            )
            return
    if employee.manager_id is None:
        return
    mgr = db.get(Employee, employee.manager_id)
    if mgr is None or mgr.user_id is None:
        return
    _push(
        db, mgr.user_id, "continuation_requested",
        f"{employee.full_name} needs continuation approval",
        f"{employee.full_name} requested continuation approval for '{sub_name}' "
        "beyond its allowed duration. No Project Head is assigned to this project.",
        req.id, target_url,
    )


def affected_report_id(db: Session, req: ContinuationRequest) -> uuid.UUID | None:
    """The report holding the work entered under this request - the rows stamped
    with its id (migration 0076), which are exactly the days the decision is
    about. Prefers the report for the continuation date itself when the activity
    was continued on more than one day, else the earliest of them.

    None when nothing was ever entered under the request: one raised through the
    explicit endpoint and decided before the employee reported that day has no
    row, and so no report to send them to.

    Once a decision has stamped req.affected_report_id (migration 0077) that
    stored value wins - after a rejection the rows it is derived from are gone,
    and recomputing would answer None. Before a decision it is computed live, so
    the stamp written at decision time is always this same answer."""
    if req.affected_report_id is not None:
        return req.affected_report_id
    rows = db.execute(
        select(DailyWorkReport.id, DailyWorkReport.report_date)
        .join(WorkReportTask, WorkReportTask.report_id == DailyWorkReport.id)
        .where(WorkReportTask.continuation_request_id == req.id)
        .distinct()
    ).all()
    if not rows:
        return None
    by_date = sorted(rows, key=lambda r: r[1])
    exact = next((rid for rid, d in by_date if d == req.continuation_date), None)
    return exact if exact is not None else by_date[0][0]


def _employee_target_url(db: Session, req: ContinuationRequest) -> str:
    """Where an approve/reject notification takes the EMPLOYEE.

    The employee's question is "what happened to my work?", so the destination is
    the REPORT the decision landed on - approved work is labelled as approved
    there, and rejected work is withdrawn from the activity list but still listed
    on the report as a "Continuation rejected" record carrying the reviewer and
    their note. The reviewer's request page (REVIEW_URL/{id}) answers a different
    question (the full request record) and stays the reviewer's destination; it
    is only used here as a fallback when no report can be resolved."""
    report_id = affected_report_id(db, req)
    return f"/work-reports/{report_id}" if report_id else f"{REVIEW_URL}/{req.id}"


def _notify_employee(db: Session, employee_id: uuid.UUID, type_: str, title: str, message: str,
                     req_id: uuid.UUID, target_url: str) -> None:
    emp = db.get(Employee, employee_id)
    if emp is None or emp.user_id is None:
        return
    _push(db, emp.user_id, type_, title, message, req_id, target_url)


# -- name/routing display resolution -----------------------------------------

def _attach_names(db: Session, rows: list[ContinuationRequest]) -> None:
    if not rows:
        return
    employee_ids = {r.employee_id for r in rows} | {r.reviewer_id for r in rows if r.reviewer_id}
    project_ids = {r.project_id for r in rows}
    sub_ids = {r.sub_activity_id for r in rows}

    employees = {
        e.id: e for e in db.execute(select(Employee).where(Employee.id.in_(employee_ids))).scalars().all()
    }
    projects = {
        p.id: p for p in db.execute(select(Project).where(Project.id.in_(project_ids))).scalars().all()
    }
    subs = {
        s.id: s for s in db.execute(select(ActivityMaster).where(ActivityMaster.id.in_(sub_ids))).scalars().all()
    }
    parent_ids = {s.parent_id for s in subs.values() if s.parent_id}
    parents = (
        {p.id: p for p in db.execute(select(ActivityMaster).where(ActivityMaster.id.in_(parent_ids))).scalars().all()}
        if parent_ids else {}
    )

    for r in rows:
        emp = employees.get(r.employee_id)
        proj = projects.get(r.project_id)
        sub = subs.get(r.sub_activity_id)
        parent = parents.get(sub.parent_id) if sub and sub.parent_id else None
        reviewer = employees.get(r.reviewer_id) if r.reviewer_id else None

        r.employee_name = emp.full_name if emp else ""  # type: ignore[attr-defined]
        r.project_name = proj.name if proj else ""  # type: ignore[attr-defined]
        r.project_code = proj.code if proj else ""  # type: ignore[attr-defined]
        r.sub_activity_name = sub.name if sub else ""  # type: ignore[attr-defined]
        r.activity_name = parent.name if parent else None  # type: ignore[attr-defined]
        r.reviewer_name = reviewer.full_name if reviewer else None  # type: ignore[attr-defined]

        head_id = authz.project_head_employee_id(db, r.project_id)
        if head_id is not None and head_id != r.employee_id:
            head = employees.get(head_id) or db.get(Employee, head_id)
            r.routed_to_name = head.full_name if head else None  # type: ignore[attr-defined]
            r.routed_to_role = "head"  # type: ignore[attr-defined]
        elif emp is not None and emp.manager_id is not None:
            mgr = employees.get(emp.manager_id) or db.get(Employee, emp.manager_id)
            r.routed_to_name = mgr.full_name if mgr else None  # type: ignore[attr-defined]
            r.routed_to_role = "manager"  # type: ignore[attr-defined]
        else:
            r.routed_to_name = None  # type: ignore[attr-defined]
            r.routed_to_role = None  # type: ignore[attr-defined]


# -- the gate work_items.py consults -----------------------------------------

def has_approved_continuation(db: Session, *, work_item_id: uuid.UUID) -> bool:
    """Whether an APPROVED continuation request exists for this work item -
    the single predicate work_items.resolve_task_work_item gates on once the
    item's allowed duration is spent in work days. Approval is permanent for
    the life of the item: work days only accumulate, so an item that has spent
    its allowance never falls back inside it."""
    return db.execute(
        select(ContinuationRequest.id).where(
            ContinuationRequest.work_item_id == work_item_id,
            ContinuationRequest.status == ContinuationRequestStatus.approved.value,
        ).limit(1)
    ).first() is not None


def latest_requests_by_work_item(
    db: Session, work_item_ids,
) -> dict[uuid.UUID, ContinuationRequest]:
    """The most recent continuation request per work item (any status) - the
    one reflecting each item's CURRENT continuation-approval state. Consumed
    by work_items.get_open_work_items to annotate open-task suggestions."""
    ids = list(work_item_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(ContinuationRequest)
        .where(ContinuationRequest.work_item_id.in_(ids))
        .order_by(ContinuationRequest.requested_at)
    ).scalars().all()
    latest: dict[uuid.UUID, ContinuationRequest] = {}
    for r in rows:
        latest[r.work_item_id] = r  # later rows overwrite earlier ones
    _attach_names(db, list(latest.values()))
    return latest


def rejected_requests_by_report(
    db: Session, report_ids,
) -> dict[uuid.UUID, list[ContinuationRequest]]:
    """The REJECTED continuation requests each report carries, display names
    attached, grouped by report.

    Rejection withdraws the rows entered under the request, so the request record
    is all that is left of it - and it is what the report detail shows the
    employee so a refused continuation does not just vanish from their history.
    Keyed on affected_report_id, stamped at decision time (migration 0077)
    precisely because the rows it was derived from no longer exist.

    One query for the whole page (plus _attach_names' batch), and it lives here
    rather than in work_reports so every read of continuation state goes through
    this module."""
    ids = list(report_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(ContinuationRequest)
        .where(
            ContinuationRequest.affected_report_id.in_(ids),
            ContinuationRequest.status == ContinuationRequestStatus.rejected.value,
        )
        .order_by(ContinuationRequest.decided_at)
    ).scalars().all()
    if not rows:
        return {}
    _attach_names(db, list(rows))
    out: dict[uuid.UUID, list[ContinuationRequest]] = {}
    for req in rows:
        out.setdefault(req.affected_report_id, []).append(req)
    return out


def _pending_for_work_item(db: Session, work_item_id: uuid.UUID) -> ContinuationRequest | None:
    return db.execute(
        select(ContinuationRequest).where(
            ContinuationRequest.work_item_id == work_item_id,
            ContinuationRequest.status == ContinuationRequestStatus.pending.value,
        )
    ).scalar_one_or_none()


def pending_request_for_work_item(
    db: Session, work_item_id: uuid.UUID
) -> ContinuationRequest | None:
    """The undecided request for this work item, if any. The one predicate
    behind "is this activity's continuation still awaiting a decision?" -
    consumed by work_items.has_pending_continuation (which blocks completing an
    activity on unapproved work) as well as by the create/save paths here."""
    return _pending_for_work_item(db, work_item_id)


def latest_request_for_work_item(
    db: Session, work_item_id: uuid.UUID
) -> ContinuationRequest | None:
    """The single most recent continuation request for one work item (any
    status), or None if none exists yet - the request that governs the item's
    CURRENT continuation state.

    Deliberately does NOT go through latest_requests_by_work_item: that one
    attaches display names (four extra queries) for the open-tasks surface,
    and this is called on the report-save hot path for every lump-sum row that
    has spent its allowance, where no name is ever read."""
    return db.execute(
        select(ContinuationRequest)
        .where(ContinuationRequest.work_item_id == work_item_id)
        .order_by(ContinuationRequest.requested_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def get_or_create_pending_for_continuation(
    db: Session, *, item: WorkItem, continuation_date,
) -> tuple[ContinuationRequest, bool]:
    """Called from the report-save gate (work_items.resolve_task_work_item),
    NOT from the HTTP endpoint — when an over-allowance lump-sum
    continuation is being saved and no pending/approved/rejected request
    already governs this work item. Auto-creates a pending request so the
    employee never has to file one separately; idempotent against the same
    partial-unique-index race the explicit endpoint already handles.

    Returns (request, created_now). created_now is False when an existing
    pending request was reused — the caller uses this to decide whether a
    notification is owed.

    CRITICAL: this function must NEVER call db.commit() or send a
    notification itself. It runs INSIDE work_reports.service's
    create_work_report/update_work_report transaction, before that
    function's own single terminal db.commit() — an early commit here would
    partially commit a report save that might still fail validation on a
    later row. Use db.add(...) + db.flush() only, exactly like the START
    branch of resolve_task_work_item does for a fresh WorkItem. The caller
    (work_reports.service, after ITS OWN commit succeeds) is responsible for
    calling notify_new_pending_request for any (request, True) this
    returns — mirroring how leave/service.py always commits the main entity
    first and calls its notify_* helpers afterward.

    The speculative insert below is wrapped in a SAVEPOINT (db.begin_nested())
    rather than relying on a plain db.rollback(). This function is called
    mid-transaction — potentially after the report row itself, prior periods,
    and prior work items from earlier tasks in the same multi-task/multi-period
    report save have already been db.add()-ed and db.flush()-ed but not yet
    committed (create_work_report/update_work_report each have exactly ONE
    terminal db.commit(), at the very end). A plain db.rollback() operates on
    the WHOLE transaction, not just this statement, so losing the race here
    would silently discard everything already flushed earlier in the SAME
    report save while the caller's loop keeps referencing those now-reverted
    ORM objects. This does NOT mirror create_continuation_request's own
    IntegrityError handling — that function is only ever called standalone,
    with nothing else pending in its session, so a plain rollback there is
    safe. A SAVEPOINT confines the rollback-on-conflict to just this insert
    attempt.
    """
    existing = _pending_for_work_item(db, item.id)
    if existing is not None:
        return existing, False
    req = ContinuationRequest(
        employee_id=item.employee_id,
        work_item_id=item.id,
        project_id=item.project_id,
        sub_activity_id=item.sub_activity_id,
        original_report_date=item.started_on,
        allowed_duration_days=item.target_days,
        due_date=item.due_date,
        continuation_date=continuation_date,
        status=ContinuationRequestStatus.pending.value,
    )
    try:
        with db.begin_nested():
            db.add(req)
            db.flush()
    except IntegrityError:
        # Lost the race to a concurrent duplicate create/save — the partial
        # unique index rejected the second pending row. Exiting the `with`
        # block on this exception automatically rolls back only the nested
        # SAVEPOINT (this insert attempt), never anything already flushed
        # earlier in the enclosing report-save transaction (the report row,
        # prior periods, prior work items from earlier tasks in the same
        # multi-task/multi-period save). Fall back to the winner.
        existing = _pending_for_work_item(db, item.id)
        if existing is None:
            raise
        return existing, False
    return req, True


def notify_new_pending_request(db: Session, req: ContinuationRequest) -> None:
    """Fire the same 'continuation_requested' notification
    create_continuation_request sends, for a request that was instead
    auto-created inside a report save. Call this ONLY after the caller's own
    outer transaction has already committed (see
    get_or_create_pending_for_continuation's docstring) — _notify_reviewer
    does its own internal commit via _push, which is safe once there is
    nothing else left uncommitted in this session."""
    employee = db.get(Employee, req.employee_id)
    if employee is None:
        return
    sub = db.get(ActivityMaster, req.sub_activity_id)
    _notify_reviewer(db, employee, req, sub.name if sub else "this activity")


def _withdrawal_summary(withdrawn: list[dict]) -> str:
    """The sentence appended to the rejection notification telling the employee
    what happened to the work they had already entered. Silent when nothing was
    withdrawn - a request raised through the explicit endpoint before any entry
    was saved has no rows to remove, and inventing a sentence about it would be
    a lie."""
    if not withdrawn:
        return ""
    dates = ", ".join(str(w["report_date"]) for w in sorted(
        withdrawn, key=lambda w: w["report_date"]
    ))
    reopened = [w for w in withdrawn if w["reopened"]]
    msg = f" The entry has been removed from your report for {dates}."
    if reopened:
        msg += (
            " That report has been reopened for editing because it has no other "
            "activity left."
            if len(reopened) == 1
            else " Those reports have been reopened for editing because they have "
                 "no other activity left."
        )
    return msg


def _fetch(db: Session, req_id: uuid.UUID) -> ContinuationRequest:
    req = db.get(ContinuationRequest, req_id)
    if req is None:
        raise AppError("not_found", "Continuation request not found.", 404)
    return req


def _fetch_locked(db: Session, req_id: uuid.UUID) -> ContinuationRequest:
    req = db.execute(
        select(ContinuationRequest).where(ContinuationRequest.id == req_id).with_for_update()
    ).scalar_one_or_none()
    if req is None:
        raise AppError("not_found", "Continuation request not found.", 404)
    return req


# -- public API ---------------------------------------------------------------

def create_continuation_request(
    db: Session, actor: User, data: ContinuationRequestCreate
) -> ContinuationRequest:
    employee = _current_employee(db, actor)
    if employee is None:
        raise AppError("forbidden", "Only employees can request continuation approval.", 403)

    item = db.get(WorkItem, data.work_item_id)
    if item is None:
        raise AppError("not_found", "Work item not found.", 404)
    if item.employee_id != employee.id:
        raise AppError("forbidden", "You can only request continuation for your own tasks.", 403)
    if item.completed_on is not None:
        raise AppError("validation_error", "This task is already completed.", 422)
    # The allowed duration is spent in WORK DAYS - the distinct report dates the
    # activity was actually worked on - not in calendar days since it started.
    # The continuation date itself is excluded: it is the day being asked for,
    # not a day already used. Same predicate the save-time gate applies, so the
    # request surface and the block can never disagree.
    days_used = count_work_days(
        db, item_id=item.id, excluding=data.continuation_date
    )
    if not lumpsum_allowance_exhausted(days_used, item.target_days):
        raise AppError(
            "validation_error",
            "This task is still within its allowed duration - no approval is needed yet.",
            422,
        )

    # Idempotent: a retry (double click / refresh) must not create a second
    # pending request for the same situation - return the existing one.
    existing = _pending_for_work_item(db, item.id)
    if existing is not None:
        _attach_names(db, [existing])
        return existing

    sub = db.get(ActivityMaster, item.sub_activity_id)
    req = ContinuationRequest(
        employee_id=employee.id,
        work_item_id=item.id,
        project_id=item.project_id,
        sub_activity_id=item.sub_activity_id,
        original_report_date=item.started_on,
        allowed_duration_days=item.target_days,
        due_date=item.due_date,
        continuation_date=data.continuation_date,
        status=ContinuationRequestStatus.pending.value,
    )
    db.add(req)
    try:
        db.commit()
    except IntegrityError:
        # Lost the race to a concurrent duplicate create - the partial unique
        # index rejected the second pending row. Fall back to the winner.
        db.rollback()
        existing = _pending_for_work_item(db, item.id)
        if existing is None:
            raise
        _attach_names(db, [existing])
        return existing
    db.refresh(req)

    _attach_names(db, [req])
    _notify_reviewer(db, employee, req, sub.name if sub else "this activity")
    return req


def _reviewable_project_ids_or_all(db: Session, actor: User) -> set[uuid.UUID] | None:
    """None means 'no project filter' - PM reviews everything."""
    if actor.role == UserRole.project_manager:
        return None
    return authz.reviewable_project_ids(db, actor)


def list_pending(db: Session, actor: User) -> list[ContinuationRequest]:
    project_ids = _reviewable_project_ids_or_all(db, actor)
    if project_ids is not None and not project_ids:
        return []
    stmt = select(ContinuationRequest).where(
        ContinuationRequest.status == ContinuationRequestStatus.pending.value
    )
    if project_ids is not None:
        stmt = stmt.where(ContinuationRequest.project_id.in_(project_ids))
    me = _current_employee(db, actor)
    if me is not None:
        # A reviewer never sees their own request in the queue they'd have to
        # act on - they cannot approve it anyway (self-review is forbidden).
        stmt = stmt.where(ContinuationRequest.employee_id != me.id)
    rows = list(db.execute(stmt.order_by(ContinuationRequest.requested_at)).scalars().all())
    _attach_names(db, rows)
    return rows


def list_all(
    db: Session, actor: User, *, status: str | None, limit: int, offset: int,
) -> tuple[list[ContinuationRequest], int]:
    project_ids = _reviewable_project_ids_or_all(db, actor)
    if project_ids is not None and not project_ids:
        return [], 0
    stmt = select(ContinuationRequest)
    if project_ids is not None:
        stmt = stmt.where(ContinuationRequest.project_id.in_(project_ids))
    if status is not None:
        stmt = stmt.where(ContinuationRequest.status == status)
    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = list(
        db.execute(
            stmt.order_by(ContinuationRequest.requested_at.desc()).limit(limit).offset(offset)
        ).scalars().all()
    )
    _attach_names(db, rows)
    return rows, total


def _assert_can_review(db: Session, actor: User, req: ContinuationRequest) -> None:
    if not authz.can_review_report(db, actor, {req.project_id}):
        raise AppError(
            "forbidden",
            "Only a project manager or this request's assigned Project Head can review it.",
            403,
        )
    me = _current_employee(db, actor)
    if me is not None and req.employee_id == me.id:
        raise AppError(
            "forbidden",
            "You can't review your own continuation request - another reviewer has to decide it.",
            403,
        )


def get_continuation_request(db: Session, actor: User, req_id: uuid.UUID) -> ContinuationRequest:
    req = _fetch(db, req_id)
    if actor.role != UserRole.project_manager:
        me = _current_employee(db, actor)
        is_owner = me is not None and req.employee_id == me.id
        if not is_owner and not authz.can_review_report(db, actor, {req.project_id}):
            raise AppError("forbidden", "Not permitted.", 403)
    _attach_names(db, [req])
    return req


def approve_continuation_request(
    db: Session, actor: User, req_id: uuid.UUID, comment: str | None
) -> ContinuationRequest:
    req = _fetch_locked(db, req_id)
    _assert_can_review(db, actor, req)
    if req.status != ContinuationRequestStatus.pending.value:
        raise AppError("validation_error", "This request has already been decided.", 422)

    # Approval is a decision about the SAME lump-sum activity, nothing more: it
    # deliberately touches no WorkItem. The rows already entered under this
    # request keep their continuation_request_id and simply start reading as
    # approved work, still linked to the original work item, with its original
    # started_on/due_date and its already-spent work days. No new work item is
    # created and no fresh allowance is granted - continuing further days rides
    # on this same approval (latest_request_for_work_item returns it).
    reviewer = _current_employee(db, actor)
    req.status = ContinuationRequestStatus.approved.value
    req.reviewer_id = reviewer.id if reviewer else None
    req.decision_comment = comment
    req.decided_at = datetime.now(timezone.utc)
    req.affected_report_id = affected_report_id(db, req)
    db.add(req)
    db.commit()
    db.refresh(req)

    _attach_names(db, [req])
    sub = db.get(ActivityMaster, req.sub_activity_id)
    _notify_employee(
        db, req.employee_id, "continuation_approved", "Continuation approved",
        f"Your request to continue '{sub.name if sub else 'this activity'}' beyond "
        "its allowed duration was approved. You can continue reporting it.",
        req.id, _employee_target_url(db, req),
    )
    return req


def reject_continuation_request(
    db: Session, actor: User, req_id: uuid.UUID, comment: str | None
) -> ContinuationRequest:
    req = _fetch_locked(db, req_id)
    _assert_can_review(db, actor, req)
    if req.status != ContinuationRequestStatus.pending.value:
        raise AppError("validation_error", "This request has already been decided.", 422)

    reviewer = _current_employee(db, actor)
    req.status = ContinuationRequestStatus.rejected.value
    req.reviewer_id = reviewer.id if reviewer else None
    req.decision_comment = comment
    req.decided_at = datetime.now(timezone.utc)
    # Stamped BEFORE the withdrawal below deletes the rows it is derived from -
    # this is what keeps the rejection visible on that report afterwards.
    req.affected_report_id = affected_report_id(db, req)
    db.add(req)

    # A rejected continuation is not accepted work, so it must not stay on the
    # report looking like accepted work. Withdraw exactly the rows entered under
    # this request - never the whole report, never another activity on it. Done
    # BEFORE the commit so the decision and its consequence are one transaction:
    # a rejection that recorded itself but left the work behind is the bug this
    # phase exists to fix. work_reports.service is imported lazily because it
    # imports this module at load time.
    from app.modules.work_reports import service as work_reports_service

    sub = db.get(ActivityMaster, req.sub_activity_id)
    sub_name = sub.name if sub else "this activity"
    # Resolved BEFORE the withdrawal deletes the stamped rows it is read from.
    target_url = _employee_target_url(db, req)
    withdrawn = work_reports_service.withdraw_continuation_rows(
        db,
        continuation_request_id=req.id,
        reviewer_user_id=actor.id,
        note=(
            f"Continuation of '{sub_name}' beyond its allowed duration was "
            "rejected, and the entry was removed from this report."
        ),
    )

    db.commit()
    db.refresh(req)

    _attach_names(db, [req])
    _notify_employee(
        db, req.employee_id, "continuation_rejected", "Continuation rejected",
        f"Your request to continue '{sub_name}' beyond its allowed duration was "
        "rejected"
        + (f": {comment}" if comment else ".")
        + " You cannot continue this activity."
        + _withdrawal_summary(withdrawn),
        req.id, target_url,
    )
    return req
