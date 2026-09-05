"""The "All Requests" view's single scoped read: Leave AND Permission, one page.

WHAT THIS IS
============
Phase 4F renamed the "All leave" tab to "All Requests" and put permission
requests in it beside leave. It is a HISTORY view, not an approval queue: every
status appears, and nothing here approves, rejects, cancels, notifies or emails
anything. `GET /api/v1/all-requests` is the only thing this module exposes.

WHY IT IS ONE ENDPOINT AND NOT TWO CALLS MERGED IN THE BROWSER
==============================================================
Both source lists are paged and filtered SERVER-side. Two independently paged
lists cannot be merged into one correctly paged list in the client without
over-fetching, and over-fetching has a ceiling (`limit` maxes at 100) past which
rows are silently dropped - precisely the failure this view must not have. One
UNION, one ORDER BY, one LIMIT/OFFSET and one total is exactly correct at every
page instead.

AUTHORISATION IS NOT REIMPLEMENTED HERE
=======================================
The two scope rules are the modules' OWN, called directly:

    leave_service._apply_scope        (leave_requests)
    permission_service._apply_scope   (permission_requests)

Both take a select and return it with their `WHERE` added, so passing a
column-select instead of an entity-select gets the identical predicate. That
means:

    project manager  every row of both tables
    Project Head     their own rows, plus rows whose `routed_project_id` is a
                     project THEY head (`authz.reviewable_project_ids`) - never
                     another Head's
    employee         their own rows only

`Employee.manager_id` and `Employee.reporting_pm_id` are NOT consulted; neither
scope rule has ever used them and nothing here adds them. A reader who is denied
by either rule simply contributes no rows from that table.

THE UNION'S SHAPE
=================
Leave's period is a range, a permission's is a single day, so the two are carried
in the same two columns - `from_date`/`to_date`, equal to each other for a
permission. That makes the date window ONE test for both kinds, and it is the
overlap test `leave/service.list_leave_requests` already applies:

    to_date >= date_from AND from_date <= date_to

For a permission both sides collapse to `permission_date`, which is exactly the
containment test `permissions/service.list_permission_requests` applies. Neither
module's existing filter semantics changes.

`status` is carried as text because the two enums are distinct Postgres types
with identical members; the API takes the shared member name and applies it to
both tables.

WHAT THE "By" COLUMN READS
==========================
`manager_id` on both tables, resolved to a name here - the ACTUAL actor each
module stamps at decision time, never the routed recipient or a current
post-holder. Which statuses are allowed to SHOW that actor is a display decision
and stays in the frontend, where Leave's has always lived
(`leave/types.ts::leaveDecisionActor`).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import String, cast, func, literal, null, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.leave import service as leave_service
from app.modules.leave.classification import LeaveClassification, classify_leave
from app.modules.leave.effects import leave_working_days
from app.modules.leave.models import LeaveHalfDayPeriod, LeaveRequest, LeaveStatus
from app.modules.permissions import service as permission_service
from app.modules.permissions.models import (
    PermissionPeriod,
    PermissionRequest,
    PermissionStatus,
)
from app.modules.users.models import User

router = APIRouter(prefix="/all-requests", tags=["leave"])

# The five statuses BOTH kinds share, by member name. Declared once so the query
# parameter can be validated against one list rather than against two enums that
# happen to agree.
SHARED_STATUSES = tuple(s.value for s in LeaveStatus)


class AllRequestOut(BaseModel):
    """One row of the All Requests table, of either kind.

    `kind` is the discriminator every consumer branches on - which detail page a
    row opens, and how its Type cell is composed. The kind-specific fields are
    null on the other kind and the frontend renders them through the label maps
    each module already owns, so no display string is invented here.
    """

    id: uuid.UUID
    kind: str  # "leave" | "permission"
    employee_id: uuid.UUID
    employee_name: str | None = None
    # A leave's period; for a permission both are its single `permission_date`.
    from_date: date
    to_date: date
    status: str
    reason: str | None = None
    # The ACTUAL decision actor, from the row's own `manager_id`.
    manager_id: uuid.UUID | None = None
    manager_name: str | None = None
    created_at: datetime
    # Leave only: Normal/Special, derived from the working-day count exactly as
    # `leave/service.attach_computed_fields` derives it for the Leave list.
    classification: LeaveClassification | None = None
    working_days: int | None = None
    # Leave only: which half of the day, when the request is half a day. Carried
    # because the Type cell is composed from BOTH this and `classification` - a
    # half-day request classifies Normal (one working day is <= 3), so without it
    # this table would keep labelling one "Normal" exactly as every other Type
    # surface did.
    half_day_period: LeaveHalfDayPeriod | None = None
    # Permission only: the selected half, and what it costs.
    period: PermissionPeriod | None = None
    duration_hours: int | None = None


class AllRequestPage(BaseModel):
    items: list[AllRequestOut]
    total: int
    limit: int
    offset: int


def _leave_select(db: Session, actor: User):
    """Leave rows in the union's shape, scoped by LEAVE's own rule."""
    stmt = select(
        LeaveRequest.id.label("id"),
        literal("leave").label("kind"),
        LeaveRequest.employee_id.label("employee_id"),
        LeaveRequest.start_date.label("from_date"),
        LeaveRequest.end_date.label("to_date"),
        cast(LeaveRequest.status, String).label("status"),
        LeaveRequest.reason.label("reason"),
        LeaveRequest.manager_id.label("manager_id"),
        LeaveRequest.created_at.label("created_at"),
        # Cast to text like `status` above, so the two halves of the union carry
        # the same column type on both sides; re-typed on the way out.
        cast(LeaveRequest.half_day_period, String).label("half_day_period"),
        cast(null(), String).label("period"),
        cast(null(), String).label("duration_hours"),
    )
    return leave_service._apply_scope(db, actor, stmt)


def _permission_select(db: Session, actor: User):
    """Permission rows in the union's shape, scoped by PERMISSION's own rule."""
    stmt = select(
        PermissionRequest.id.label("id"),
        literal("permission").label("kind"),
        PermissionRequest.employee_id.label("employee_id"),
        PermissionRequest.permission_date.label("from_date"),
        PermissionRequest.permission_date.label("to_date"),
        cast(PermissionRequest.status, String).label("status"),
        PermissionRequest.reason.label("reason"),
        PermissionRequest.manager_id.label("manager_id"),
        PermissionRequest.created_at.label("created_at"),
        # A permission is never half a DAY - its own `period` says which half of
        # the day it covers, in hours. Null keeps the union's shape.
        cast(null(), String).label("half_day_period"),
        cast(PermissionRequest.period, String).label("period"),
        cast(PermissionRequest.duration_hours, String).label("duration_hours"),
    )
    return permission_service._apply_scope(db, actor, stmt)


def _names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """One batched id -> "First Last" map for every name on the page.

    Both the requester and the actor come out of it, so the two columns cannot
    render the same person differently - the same reason both modules resolve
    their names server-side rather than through the RBAC-scoped `GET /employees`.
    """
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return {
        row.id: f"{row.first_name} {row.last_name}".strip()
        for row in db.execute(
            select(Employee.id, Employee.first_name, Employee.last_name).where(
                Employee.id.in_(wanted)
            )
        ).all()
    }


def list_all_requests(
    db: Session,
    actor: User,
    *,
    employee_id: uuid.UUID | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 20,
    offset: int = 0,
    exclude_self: bool = False,
) -> AllRequestPage:
    """One scoped, filtered, ordered page across both request kinds."""
    leave_stmt, leave_allowed = _leave_select(db, actor)
    perm_stmt, perm_allowed = _permission_select(db, actor)

    me = _current_employee(db, actor) if exclude_self else None
    if exclude_self and me is not None:
        leave_stmt = leave_stmt.where(LeaveRequest.employee_id != me.id)
        perm_stmt = perm_stmt.where(PermissionRequest.employee_id != me.id)

    if employee_id is not None:
        leave_stmt = leave_stmt.where(LeaveRequest.employee_id == employee_id)
        perm_stmt = perm_stmt.where(PermissionRequest.employee_id == employee_id)

    if status:
        # Applied to each table through its OWN enum, so the comparison is a
        # typed one on both sides rather than a cast-to-text scan.
        leave_stmt = leave_stmt.where(LeaveRequest.status == LeaveStatus(status))
        perm_stmt = perm_stmt.where(
            PermissionRequest.status == PermissionStatus(status)
        )

    # The window is the OVERLAP test Leave already uses. A permission's two dates
    # are the same day, so for it this is the containment test Permission already
    # uses - neither module's meaning changes.
    if date_from is not None:
        leave_stmt = leave_stmt.where(LeaveRequest.end_date >= date_from)
        perm_stmt = perm_stmt.where(PermissionRequest.permission_date >= date_from)
    if date_to is not None:
        leave_stmt = leave_stmt.where(LeaveRequest.start_date <= date_to)
        perm_stmt = perm_stmt.where(PermissionRequest.permission_date <= date_to)

    parts = []
    if leave_allowed:
        parts.append(leave_stmt)
    if perm_allowed:
        parts.append(perm_stmt)
    if not parts:
        return AllRequestPage(items=[], total=0, limit=limit, offset=offset)

    union = (
        parts[0].union_all(*parts[1:]) if len(parts) > 1 else parts[0]
    ).subquery("all_requests")

    total = db.execute(select(func.count()).select_from(union)).scalar_one()
    # `id` breaks the tie so two rows created in the same instant - and a leave
    # and a permission filed together - keep ONE stable order across pages.
    rows = db.execute(
        select(union)
        .order_by(union.c.created_at.desc(), union.c.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    people = _names(
        db,
        {r.employee_id for r in rows} | {r.manager_id for r in rows},
    )

    items: list[AllRequestOut] = []
    for r in rows:
        is_leave = r.kind == "leave"
        # Derived, never stored, exactly as the Leave list derives it - so a
        # historical request classifies correctly with no backfill and cannot go
        # stale when the company calendar moves.
        working_days = (
            len(leave_working_days(db, r.from_date, r.to_date)) if is_leave else None
        )
        items.append(
            AllRequestOut(
                id=r.id,
                kind=r.kind,
                employee_id=r.employee_id,
                employee_name=people.get(r.employee_id),
                from_date=r.from_date,
                to_date=r.to_date,
                status=r.status,
                reason=r.reason,
                manager_id=r.manager_id,
                manager_name=people.get(r.manager_id) if r.manager_id else None,
                created_at=r.created_at,
                classification=classify_leave(working_days) if is_leave else None,
                working_days=working_days,
                half_day_period=(
                    LeaveHalfDayPeriod(r.half_day_period)
                    if is_leave and r.half_day_period
                    else None
                ),
                period=PermissionPeriod(r.period) if r.period else None,
                duration_hours=int(r.duration_hours) if r.duration_hours else None,
            )
        )

    return AllRequestPage(items=items, total=total, limit=limit, offset=offset)


@router.get("", response_model=AllRequestPage)
def get_all_requests(
    employee_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(
        default=None,
        description="One of the five statuses both kinds share: pending, "
        "approved, rejected, cancelled, cancellation_requested.",
    ),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    exclude_self: bool = Query(
        default=False,
        description="Drop the caller's own requests - what a Project Head's "
        "reused panel passes, same flag as /leave-requests.",
    ),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AllRequestPage:
    """The All Requests history: leave and permission rows, newest first.

    Read-only, and scoped by each module's own rule - see this file's header.
    An unknown `status` is treated as no filter rather than as an error, the
    same way a stale value in the URL has always been ignored by these lists.
    """
    return list_all_requests(
        db,
        current,
        employee_id=employee_id,
        status=status if status in SHARED_STATUSES else None,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
        exclude_self=exclude_self,
    )
