"""Who a leave request is routed to, and where they read it.

THE ONE CHAIN
=============
Every notification channel - the in-app bell today, email as of this phase, and
anything added later - resolves its recipient by walking
:func:`resolve_leave_recipients`. Nothing re-derives "the Head, else the
PM" on its own. That is the whole reason this module exists as its own
file: `leave/service.py` (in-app) and `leave/email.py` (email) both import it,
and neither imports the other, so the two channels cannot drift into different
Head/fallback logic.

PEOPLE, NOT ADDRESSES
=====================
The chain resolves EMPLOYEES and applies no channel-specific reachability test.
Each channel walks the same ordered list and takes the first candidate it can
actually deliver to - the bell needs a linked `user_id`, email needs a
`work_email`. This is deliberate: a Head with a login but no work email still
gets the bell notification, while only the email falls through to the PM.
Collapsing this to a single pre-resolved recipient would force one channel to
adopt the other's failure mode. Each channel still notifies exactly ONE person;
the chain is a fallback order, not a broadcast list.

WHAT IT DOES NOT DO
===================
It does not decide who may APPROVE anything. Approval authority is
`leave/service.py::_assert_can_review` -> `core/authz.py::can_review_report`,
which reads `Project.head_employee_id` directly and is not affected by anything
here. A fallback rung is a delivery decision only: the Project Head remains the
intended per-project approver even when the email goes to somebody else.

It also does not resolve the PROJECT. That is
`leave/routing.py::resolve_routed_project`, run once at submission time and
stored on `LeaveRequest.routed_project_id`; this module only reads that column.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import authz
from app.modules.employees.models import Employee
from app.modules.leave.models import LeaveRequest


@dataclass(frozen=True)
class LeaveRecipient:
    """One candidate approver for a leave request.

    `is_head` says which rung of the chain this is - the routed project's Head,
    or the PM fallback - and picks the deep-link shape in
    :func:`leave_request_path`.
    """

    employee: Employee
    is_head: bool


def _reporting_pm_employee(db: Session, employee: Employee) -> Employee | None:
    """The employee record of the requester's reporting PM, or None.

    `Employee.reporting_pm_id` is a **users.id**, not an employees.id, so it is
    resolved back to the PM's employee row: the bell needs a `user_id` (which
    we already have) but the email needs a `work_email`, which only the employee
    record carries.
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


def resolve_leave_recipients(
    db: Session, employee: Employee, req: LeaveRequest
) -> list[LeaveRecipient]:
    """The ordered approver candidates for `req`: the routed project's CURRENT
    Head first, then the requester's reporting PM.

    The Head is resolved fresh from `routed_project_id` on every call, never read
    off a value frozen at submission time, so a Head reassignment after this
    request was filed is honoured (Phase 1 spec §15). A Head who IS the requester
    is dropped: nobody is notified about - or reviews - their own leave. (Routing
    already returns None for a Head's own request, so `routed_project_id` is
    NULL there; the check stays for rows written before that rule existed.)

    THE FALLBACK RUNG IS THE REPORTING PM
    -------------------------------------
    `Employee.reporting_pm_id`, and deliberately NOT `Employee.manager_id`, which
    this rung used to read. `manager_id` is the LINE MANAGER, who is not an
    authorized leave reviewer: `service._assert_can_review` grants review to a PM
    (any request) or the routed project's Head, and to nobody else. Notifying a
    line manager therefore told somebody who could not act, while the PM who
    could act was never told - and on live data `manager_id` is set on 3 of 29
    employees against 29 of 29 for `reporting_pm_id`, so in practice the fallback
    resolved to nobody at all and the request went out silently.

    `reporting_pm_id` points at a `project_manager` user, so every recipient this
    function returns can actually perform the approval they are being notified
    about. It is also the pointer the rest of the codebase already uses to reach
    a PM (`activity_requests.service._pm_user_ids`,
    `reminders.daily_report.service`).

    ONE RECIPIENT PER CHANNEL, NOT A BROADCAST
    ------------------------------------------
    The list is ordered candidates, not an audience. Each channel takes the FIRST
    entry it can deliver to and stops - the bell needs a linked `user_id`, email
    needs a `work_email` - so exactly one person is notified per channel. The
    second rung exists only for when the first is undeliverable on that channel
    (a Head with no login still gets the email; the bell goes to the PM).

    A PM who is the requester is dropped for the same reason a self-Head is: they
    cannot review their own leave. An empty list means nobody could be resolved,
    which is a legitimate outcome and never an error.
    """
    out: list[LeaveRecipient] = []
    head_id = (
        authz.project_head_employee_id(db, req.routed_project_id)
        if req.routed_project_id is not None
        else None
    )
    if head_id is not None and head_id != employee.id:
        head = db.get(Employee, head_id)
        if head is not None:
            out.append(LeaveRecipient(employee=head, is_head=True))
    pm = _reporting_pm_employee(db, employee)
    if pm is not None and pm.id != employee.id:
        out.append(LeaveRecipient(employee=pm, is_head=False))
    return out


def resolve_in_app_recipient(
    db: Session, employee: Employee, req: LeaveRequest
) -> LeaveRecipient | None:
    """The ONE person the in-app channel delivers this request to, or None.

    The chain above is an ordered list of candidates; this applies the bell's own
    reachability test to it - a linked `user_id` - and stops at the first that
    passes, which is precisely what `service._notify_routed_approver` has always
    done inline. It is extracted here so that the "Routed to" line the leave
    detail page shows the EMPLOYEE and the notification that actually reached
    somebody are answered by one function. A page that named a different person
    from the one who got the request would be worse than no page at all, and two
    copies of a four-line loop is all it would take.

    Email is deliberately NOT folded in: it tests `work_email`, not `user_id`,
    and may legitimately land on a different rung (see the module docstring).
    """
    for candidate in resolve_leave_recipients(db, employee, req):
        if candidate.employee.user_id is not None:
            return candidate
    return None


def leave_request_path(
    req: LeaveRequest, *, is_head: bool, queue: str | None = None
) -> str:
    """The in-app path this request is reached at, for the given recipient rung.

    In one place so the notification's `target_url` and the email's link cannot
    disagree. The two shapes are pre-existing and deliberately NOT unified: the
    Head rung always names a queue, defaulting to `pending` (the queue a freshly
    submitted or cancelled request is actually in), while the fallback rung omits
    `&queue=` entirely unless a caller asked for one. A caller whose notification
    is about something NOT in the pending queue - namely
    `request_leave_cancellation`, which moves the request straight to
    `cancellation_requested` - passes `queue="cancellation"` so both rungs
    deep-link to the queue that can actually contain it.
    """
    if is_head:
        return f"/attendance?tab=leave&queue={queue or 'pending'}&id={req.id}"
    if queue is not None:
        return f"/attendance?tab=leave&queue={queue}&id={req.id}"
    return f"/attendance?tab=leave&id={req.id}"
