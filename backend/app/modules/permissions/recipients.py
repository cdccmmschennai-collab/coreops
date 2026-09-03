"""Who a permission request is routed to, and where they read it (Phase 4C).

THE ONE CHAIN
=============
Every notification channel for a permission request - the in-app bell (Phase 4B)
and email (Phase 4C) - resolves its recipient by walking
:func:`resolve_permission_recipients`. Nothing re-derives "the Head, else the
PM" a second time: `service.py` (in-app) and `email.py` (email) both import this
module, and neither imports the other, so the two channels cannot drift into
different Head/fallback logic - the same shape `leave/recipients.py` uses for
Leave, and for the same reason.

This is Permission's OWN copy of that shape, not an import of Leave's module.
The two features route the same way by design (per Phase 4B's spec), but they
are independent business objects with independent detail pages and independent
`routed_project_id` columns; coupling them through a shared function would make
a change meant for one silently reach the other. What IS shared, correctly, is
`leave/routing.py::resolve_routed_project` - the project-resolution algorithm
itself - which `permissions/service.py` already imports unchanged.

PEOPLE, NOT ADDRESSES
=====================
Like Leave's chain, this resolves EMPLOYEES and applies no channel-specific
reachability test itself. Each channel walks the same ordered list and takes the
first candidate it can actually deliver to - the bell needs a linked `user_id`
(:func:`resolve_in_app_recipient`), email needs a `work_email` (`email.py`).

It does not decide who may APPROVE anything - that is
`service.py::_assert_can_review`, unaffected by anything here. A fallback rung is
a delivery decision only.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import authz
from app.modules.employees.models import Employee
from app.modules.permissions.models import PermissionRequest


@dataclass(frozen=True)
class PermissionRecipient:
    """One candidate approver for a permission request.

    `is_head` says which rung of the chain this is - the routed project's Head,
    or the reporting-PM fallback.
    """

    employee: Employee
    is_head: bool


def _reporting_pm_employee(db: Session, employee: Employee) -> Employee | None:
    """The employee record of the requester's reporting PM, or None.

    `Employee.reporting_pm_id` is a **users.id**, not an employees.id, so it is
    resolved back to the PM's employee row - the bell needs the `user_id` we
    already have, the email needs the `work_email` only the employee row carries.
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


def resolve_permission_recipients(
    db: Session, employee: Employee, req: PermissionRequest
) -> list[PermissionRecipient]:
    """The ordered approver candidates for `req`: the routed project's CURRENT
    Head first, then the requester's reporting PM.

    The Head is resolved fresh from `routed_project_id` on every call, never
    frozen at submission time, so a Head reassignment after this request was
    filed is honoured. A Head who IS the requester is dropped: nobody is
    notified about - or reviews - their own permission.

    THE FALLBACK RUNG IS THE REPORTING PM, NEVER `manager_id`
    -----------------------------------------------------------
    `Employee.reporting_pm_id`, and deliberately NOT `Employee.manager_id` (the
    line manager), who is not an authorized reviewer here any more than for
    Leave: `service._assert_can_review` grants review to a PM (any request) or
    the routed project's Head, and nobody else.

    ONE RECIPIENT PER CHANNEL, NOT A BROADCAST
    -------------------------------------------
    The list is ordered candidates, not an audience. Each channel takes the
    FIRST entry it can deliver to and stops. An empty list means nobody could be
    resolved, which is a legitimate outcome and never an error.
    """
    out: list[PermissionRecipient] = []
    head_id = (
        authz.project_head_employee_id(db, req.routed_project_id)
        if req.routed_project_id is not None
        else None
    )
    if head_id is not None and head_id != employee.id:
        head = db.get(Employee, head_id)
        if head is not None:
            out.append(PermissionRecipient(employee=head, is_head=True))
    pm = _reporting_pm_employee(db, employee)
    if pm is not None and pm.id != employee.id:
        out.append(PermissionRecipient(employee=pm, is_head=False))
    return out


def resolve_in_app_recipient(
    db: Session, employee: Employee, req: PermissionRequest
) -> PermissionRecipient | None:
    """The ONE person the in-app channel delivers this request to, or None.

    Applies the bell's own reachability test - a linked `user_id` - to the chain
    above and stops at the first candidate that passes. Email is deliberately NOT
    folded in here: it tests `work_email`, not `user_id`, and may legitimately
    land on a different rung - see `email.py`.
    """
    for candidate in resolve_permission_recipients(db, employee, req):
        if candidate.employee.user_id is not None:
            return candidate
    return None


def permission_request_path(req: PermissionRequest) -> str:
    """The in-app address a notification or an email opens this request at -
    the request's own detail page, which carries the Approve/Reject actions."""
    return f"/attendance/permission/{req.id}"
