"""Who a leave request is routed to, and where they read it.

THE ONE CHAIN
=============
Every notification channel - the in-app bell today, email as of this phase, and
anything added later - resolves its recipient by walking
:func:`resolve_leave_recipients`. Nothing re-derives "the Head, else the
manager" on its own. That is the whole reason this module exists as its own
file: `leave/service.py` (in-app) and `leave/email.py` (email) both import it,
and neither imports the other, so the two channels cannot drift into different
Head/fallback logic.

PEOPLE, NOT ADDRESSES
=====================
The chain resolves EMPLOYEES and applies no channel-specific reachability test.
Each channel walks the same ordered list and takes the first candidate it can
actually deliver to - the bell needs a linked `user_id`, email needs a
`work_email`. This is deliberate: a Head with a login but no work email still
gets the bell notification, while only the email falls through to the manager.
Collapsing this to a single pre-resolved recipient would force one channel to
adopt the other's failure mode.

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

from sqlalchemy.orm import Session

from app.core import authz
from app.modules.employees.models import Employee
from app.modules.leave.models import LeaveRequest


@dataclass(frozen=True)
class LeaveRecipient:
    """One candidate approver for a leave request.

    `is_head` says which rung of the chain this is - the routed project's Head,
    or the manager fallback - and picks the deep-link shape in
    :func:`leave_request_path`.
    """

    employee: Employee
    is_head: bool


def resolve_leave_recipients(
    db: Session, employee: Employee, req: LeaveRequest
) -> list[LeaveRecipient]:
    """The ordered approver candidates for `req`: the routed project's CURRENT
    Head first, then the requester's line manager.

    The Head is resolved fresh from `routed_project_id` on every call, never read
    off a value frozen at submission time, so a Head reassignment after this
    request was filed is honoured (Phase 1 spec §15). A Head who IS the requester
    is dropped: nobody is notified about - or reviews - their own leave.

    The fallback rung is `Employee.manager_id`, the line manager. It is NOT the
    `project_managers` assignment table and NOT `reporting_pm_id`; this mirrors
    what the leave notification has always done, and what
    `continuation_requests.service._notify_reviewer` documents as the same rule.

    An empty list means nobody could be resolved at all, which is a legitimate
    outcome (no routed project and no manager on record) and never an error.
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
    if employee.manager_id is not None:
        mgr = db.get(Employee, employee.manager_id)
        if mgr is not None:
            out.append(LeaveRecipient(employee=mgr, is_head=False))
    return out


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
