"""Leave balance service - month-aware reads, PM allocation, PM correction.

RBAC (unchanged by Phase 3):
  project_manager  list all balances, set allocation, correct any balance,
                   read history
  employee         read their OWN balance only - no edit, no history, no
                   allocation

THE BALANCE IS NOT STORED HERE
==============================
Every figure this module returns comes from `ledger.month_balance`, the single
authoritative calculation. Nothing in this file adds up a balance of its own, and
nothing writes one. What it writes is the two kinds of PM DECISION the ledger
folds:

  allocation   `set_allocation` - the employee's `Leave/month`, effective-dated.
  adjustment   `set_balance`    - a signed one-off correction, stamped with a
                                  month.

WHY THE PM STILL TYPES AN ABSOLUTE NUMBER
=========================================
The Leave Balance dialog has always asked for the balance the manager WANTS, and
it still does. `set_balance` turns that target into a delta against the month's
automatic figure and stores the delta:

    adjustment = target - closing(month)

That is what makes a correction coexist with the accrual instead of replacing it.
A manager who pulls September down to 2.0 has posted "-1", not "September is now
2.0 forever": October still receives its own `Leave/month` on top of the
corrected September, and next month's allocation is untouched. Storing the target
instead would have to overwrite something, and the something would be the
automatic monthly calculation.

Every correction still writes an immutable `EmployeeLeaveBalanceHistory` row in
the same transaction - the audit trail is the one this module has always kept,
not a second one - and still notifies the employee.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.leave_balances import ledger
from app.modules.leave_balances.models import (
    EmployeeLeaveAdjustment,
    EmployeeLeaveAllocation,
    EmployeeLeaveBalanceHistory,
)
from app.modules.leave_balances.schemas import (
    LeaveAllocationOut,
    LeaveAllocationPage,
    LeaveAllocationUpdate,
    LeaveBalanceHistoryOut,
    LeaveBalanceOut,
    LeaveBalanceUpdate,
    MyLeaveBalanceOut,
)
from app.modules.users.models import User
from app.shared.errors import AppError

# CoreOps runs on one business calendar. "Which month is now" must be the Chennai
# business month, or a correction posted at 00:30 IST on 1 September would land
# in August. Same constant and same reason as `leave/service.py`.
BUSINESS_TZ = ZoneInfo("Asia/Kolkata")


def business_today() -> date:
    return datetime.now(BUSINESS_TZ).date()


def resolve_month(month: date | None) -> date:
    """The month key a request is asking about - always a first-of-month.

    `None` means the current Chennai business month. Any date inside a month
    resolves to that month, so a caller may send `2026-08-01` or `2026-08-31` and
    get the same calendar month either way. A month is a CALENDAR month, never a
    rolling 30 days: `ledger.month_start` / `month_end` bound it.
    """
    return ledger.month_start(month or business_today())


def _alive_employee(db: Session, employee_id: uuid.UUID) -> Employee:
    emp = db.execute(
        select(Employee).where(
            Employee.id == employee_id, Employee.deleted_at.is_(None)
        )
    ).scalar_one_or_none()
    if emp is None:
        raise AppError("not_found", "Employee not found.", 404)
    return emp


# ---------- "last updated" --------------------------------------------------

def _last_updated(
    db: Session, employee_ids: list[uuid.UUID]
) -> dict[uuid.UUID, datetime]:
    """When a manager last changed this employee's leave configuration.

    The most recent of their adjustments and their allocation rows - the two
    things a PM can actually do here. It deliberately does NOT move when leave is
    approved: an approval changes the balance, but "last updated" on the Leave
    Balance tab has always meant "when did someone last set this", and making an
    employee's own leave look like a manager edit would be misleading.
    """
    if not employee_ids:
        return {}
    out: dict[uuid.UUID, datetime] = {}
    adjustments = db.execute(
        select(
            EmployeeLeaveAdjustment.employee_id,
            func.max(EmployeeLeaveAdjustment.created_at),
        )
        .where(EmployeeLeaveAdjustment.employee_id.in_(employee_ids))
        .group_by(EmployeeLeaveAdjustment.employee_id)
    ).all()
    allocations = db.execute(
        select(
            EmployeeLeaveAllocation.employee_id,
            func.max(EmployeeLeaveAllocation.updated_at),
        )
        .where(EmployeeLeaveAllocation.employee_id.in_(employee_ids))
        .group_by(EmployeeLeaveAllocation.employee_id)
    ).all()
    for employee_id, stamp in [*adjustments, *allocations]:
        if stamp is None:
            continue
        current = out.get(employee_id)
        if current is None or stamp > current:
            out[employee_id] = stamp
    return out


# ---------- shaping ---------------------------------------------------------

def _balance_out(
    emp: Employee, balance: ledger.MonthBalance, last_updated: datetime | None
) -> LeaveBalanceOut:
    return LeaveBalanceOut(
        employee_id=emp.id,
        employee_code=emp.employee_code,
        employee_name=emp.full_name,
        month=balance.month,
        available_leave=float(balance.closing),
        monthly_allocation=float(balance.allocation),
        carry_forward=float(balance.carry_forward),
        adjustment=float(balance.adjustment),
        consumed=float(balance.consumed),
        in_ledger=balance.in_ledger,
        ledger_start_month=balance.ledger_start,
        last_updated=last_updated,
    )


# ---------- manager: list ---------------------------------------------------

def list_balances(
    db: Session,
    *,
    month: date | None,
    q: str | None,
    sort_dir: str,
    limit: int,
    offset: int,
) -> tuple[list[LeaveBalanceOut], int, date]:
    """All active employees with their balance FOR ONE MONTH, name-sorted.

    Only the requested page of employees is folded, so the number of ledger
    walks is bounded by the page size rather than by the headcount.
    """
    key = resolve_month(month)

    stmt = select(Employee).where(Employee.deleted_at.is_(None))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Employee.employee_code.ilike(like),
                Employee.first_name.ilike(like),
                Employee.last_name.ilike(like),
            )
        )

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()

    if sort_dir == "desc":
        order = (Employee.first_name.desc(), Employee.last_name.desc())
    else:
        order = (Employee.first_name.asc(), Employee.last_name.asc())
    employees = (
        db.execute(stmt.order_by(*order).limit(limit).offset(offset)).scalars().all()
    )

    ids = [e.id for e in employees]
    balances = ledger.closing_balances(db, ids, key)
    stamps = _last_updated(db, ids)

    items = [
        _balance_out(emp, balances[emp.id], stamps.get(emp.id)) for emp in employees
    ]
    return items, total, key


# ---------- employee: own balance ------------------------------------------

def get_my_balance(
    db: Session, actor: User, month: date | None = None
) -> MyLeaveBalanceOut:
    me = _current_employee(db, actor)
    if me is None:
        raise AppError(
            "validation_error",
            "Your account isn't linked to an employee profile.",
            422,
        )
    key = resolve_month(month)
    balance = ledger.month_balance(db, me.id, key)
    return MyLeaveBalanceOut(
        employee_id=me.id,
        month=balance.month,
        available_leave=float(balance.closing),
        monthly_allocation=float(balance.allocation),
        carry_forward=float(balance.carry_forward),
        adjustment=float(balance.adjustment),
        consumed=float(balance.consumed),
        in_ledger=balance.in_ledger,
        ledger_start_month=balance.ledger_start,
        last_updated=_last_updated(db, [me.id]).get(me.id),
    )


def get_employee_balance(
    db: Session, employee_id: uuid.UUID, month: date | None = None
) -> LeaveBalanceOut:
    """Any employee's balance for a month - managers only (gated in the router)."""
    emp = _alive_employee(db, employee_id)
    key = resolve_month(month)
    balance = ledger.month_balance(db, emp.id, key)
    return _balance_out(emp, balance, _last_updated(db, [emp.id]).get(emp.id))


# ---------- manager: correction ---------------------------------------------

def _fmt(value: Decimal | None) -> str:
    """Render a balance for display: '12.5', '-2', '0' (no trailing zeros)."""
    if value is None:
        return "0"
    return f"{float(value):g}"


def _notify_balance_change(
    db: Session,
    user_id: uuid.UUID,
    employee_id: uuid.UUID,
    old_value: Decimal,
    new_value: Decimal,
    reason: str,
) -> None:
    """In-app notification to the employee whose balance a manager changed."""
    from app.modules.notifications.service import create_notification

    body = (
        f"Your available leave changed from {_fmt(old_value)} to "
        f"{_fmt(new_value)}."
    )
    reason = reason.strip()
    if reason:
        body += f" Reason: {reason}"

    create_notification(
        db,
        user_id=user_id,
        type_="leave_balance_updated",
        title="Your leave balance was updated",
        message=body,
        entity_type="employee",
        entity_id=employee_id,
        target_url="/attendance",
    )


def set_balance(
    db: Session, actor: User, employee_id: uuid.UUID, data: LeaveBalanceUpdate
) -> LeaveBalanceOut:
    """Correct one employee's balance for one month, as a signed adjustment.

    The manager states the TARGET; this stores `target - automatic`. Two
    consequences that are the whole point of the design:

      - the monthly allocation survives the correction, so the next month still
        accrues (a correction is a term of the ledger, not a replacement for the
        configuration);
      - correcting the same month twice is two adjustment rows that SUM, and each
        one keeps its own reason and author, so no audit information is lost when
        two managers act on the same month.

    A correction that changes nothing still writes its history row - the manager
    took an action and said why - but posts no zero-valued adjustment and sends
    no notification, because nothing moved.
    """
    emp = _alive_employee(db, employee_id)
    key = resolve_month(data.month)

    # Read under the ledger's own rules, then write the difference. No lock is
    # taken: adjustments are append-only and SUM, so two concurrent corrections
    # both survive rather than one silently overwriting the other. The second
    # manager's target may be computed against a figure the first has already
    # moved, which is why both rows keep their reason and author in the history.
    before = ledger.closing_balance(db, emp.id, key)
    target = Decimal(str(data.available_leave)).quantize(Decimal("0.01"))
    delta = (target - before).quantize(Decimal("0.01"))

    if delta != 0:
        db.add(
            EmployeeLeaveAdjustment(
                employee_id=emp.id,
                effective_month=key,
                days=delta,
                reason=data.reason.strip(),
                created_by=actor.id,
            )
        )

    # The audit trail this module has always kept. Written for every correction,
    # including a no-op one.
    db.add(
        EmployeeLeaveBalanceHistory(
            employee_id=emp.id,
            old_balance=before,
            new_balance=target,
            reason=data.reason.strip(),
            updated_by=actor.id,
        )
    )

    if delta != 0 and emp.user_id is not None:
        _notify_balance_change(db, emp.user_id, emp.id, before, target, data.reason)

    db.commit()

    balance = ledger.month_balance(db, emp.id, key)
    return _balance_out(emp, balance, _last_updated(db, [emp.id]).get(emp.id))


# ---------- manager: allocation ---------------------------------------------

def set_allocation(
    db: Session, actor: User, employee_id: uuid.UUID, data: LeaveAllocationUpdate
) -> LeaveAllocationOut:
    """Set the employee's `Leave/month` from `effective_from` onwards.

    Writes a NEW row for a new effective month, which is what preserves history:
    the rate in force for January is whatever row was effective in January, and
    adding a March row cannot change that. Re-saving the SAME effective month
    updates that one row - correcting a decision, rather than leaving two
    competing rows for one month (the unique index would refuse the second
    anyway).

    Nothing else moves. An allocation change never touches an adjustment and
    never touches a balance; the next read simply folds the new rate.
    """
    emp = _alive_employee(db, employee_id)
    monthly_days = Decimal(str(data.monthly_days)).quantize(Decimal("0.01"))

    row = db.execute(
        select(EmployeeLeaveAllocation).where(
            EmployeeLeaveAllocation.employee_id == emp.id,
            EmployeeLeaveAllocation.effective_from == data.effective_from,
        )
    ).scalar_one_or_none()

    if row is None:
        row = EmployeeLeaveAllocation(
            employee_id=emp.id,
            effective_from=data.effective_from,
            monthly_days=monthly_days,
            note=data.note,
            created_by=actor.id,
        )
    else:
        row.monthly_days = monthly_days
        row.note = data.note
    db.add(row)
    db.commit()
    db.refresh(row)
    return LeaveAllocationOut.model_validate(row)


def list_allocations(
    db: Session, employee_id: uuid.UUID
) -> LeaveAllocationPage:
    """Every rate this employee has been on, newest first.

    Unpaginated on purpose: this is one row per policy change in a career, not a
    row per month, so the list is short by construction.
    """
    _alive_employee(db, employee_id)
    rows = (
        db.execute(
            select(EmployeeLeaveAllocation)
            .where(EmployeeLeaveAllocation.employee_id == employee_id)
            .order_by(EmployeeLeaveAllocation.effective_from.desc())
        )
        .scalars()
        .all()
    )
    return LeaveAllocationPage(
        items=[LeaveAllocationOut.model_validate(r) for r in rows],
        total=len(rows),
    )


# ---------- manager: history ------------------------------------------------

def list_history(
    db: Session, employee_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[LeaveBalanceHistoryOut], int]:
    _alive_employee(db, employee_id)
    stmt = select(EmployeeLeaveBalanceHistory).where(
        EmployeeLeaveBalanceHistory.employee_id == employee_id
    )

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()

    rows = (
        db.execute(
            stmt.order_by(EmployeeLeaveBalanceHistory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    names = _resolve_actor_names(db, {r.updated_by for r in rows if r.updated_by})
    items = [
        LeaveBalanceHistoryOut(
            id=r.id,
            employee_id=r.employee_id,
            old_balance=float(r.old_balance) if r.old_balance is not None else None,
            new_balance=float(r.new_balance),
            reason=r.reason,
            updated_by=r.updated_by,
            updated_by_name=names.get(r.updated_by) if r.updated_by else None,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return items, total


def _resolve_actor_names(
    db: Session, user_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Map updater user ids to a display name (employee full name, else email)."""
    if not user_ids:
        return {}
    out: dict[uuid.UUID, str] = {}
    users = db.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
    emps = (
        db.execute(
            select(Employee).where(
                Employee.user_id.in_(user_ids), Employee.deleted_at.is_(None)
            )
        )
        .scalars()
        .all()
    )
    emp_by_user = {e.user_id: e.full_name for e in emps if e.user_id}
    for u in users:
        out[u.id] = emp_by_user.get(u.id) or u.email
    return out
