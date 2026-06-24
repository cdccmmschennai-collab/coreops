"""Leave balance service (Phase 1 — manual maintenance by managers).

RBAC:
  project_manager  list all balances, edit any, read history
  employee         read own balance only (no edit, no history)

Every balance change writes an immutable EmployeeLeaveBalanceHistory row in the
same transaction as the balance update — there are no balance mutations that
bypass the history trail.
"""
import uuid
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.leave_balances.models import (
    EmployeeLeaveBalance,
    EmployeeLeaveBalanceHistory,
)
from app.modules.leave_balances.schemas import (
    LeaveBalanceHistoryOut,
    LeaveBalanceOut,
    LeaveBalanceUpdate,
    MyLeaveBalanceOut,
)
from app.modules.users.models import User
from app.shared.errors import AppError


def _alive_employee(db: Session, employee_id: uuid.UUID) -> Employee:
    emp = db.execute(
        select(Employee).where(
            Employee.id == employee_id, Employee.deleted_at.is_(None)
        )
    ).scalar_one_or_none()
    if emp is None:
        raise AppError("not_found", "Employee not found.", 404)
    return emp


# ---------- manager: list ---------------------------------------------------

def list_balances(
    db: Session, *, q: str | None, sort_dir: str, limit: int, offset: int
) -> tuple[list[LeaveBalanceOut], int]:
    """All active employees with their (optional) leave balance, name-sorted."""
    stmt = (
        select(Employee, EmployeeLeaveBalance)
        .outerjoin(
            EmployeeLeaveBalance,
            EmployeeLeaveBalance.employee_id == Employee.id,
        )
        .where(Employee.deleted_at.is_(None))
    )

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
    rows = db.execute(stmt.order_by(*order).limit(limit).offset(offset)).all()

    items = [
        LeaveBalanceOut(
            employee_id=emp.id,
            employee_code=emp.employee_code,
            employee_name=emp.full_name,
            available_leave=float(bal.available_leave) if bal else 0.0,
            last_updated=bal.updated_at if bal else None,
        )
        for emp, bal in rows
    ]
    return items, total


# ---------- employee: own balance ------------------------------------------

def get_my_balance(db: Session, actor: User) -> MyLeaveBalanceOut:
    me = _current_employee(db, actor)
    if me is None:
        raise AppError(
            "validation_error",
            "Your account isn't linked to an employee profile.",
            422,
        )
    bal = db.execute(
        select(EmployeeLeaveBalance).where(
            EmployeeLeaveBalance.employee_id == me.id
        )
    ).scalar_one_or_none()
    return MyLeaveBalanceOut(
        employee_id=me.id,
        available_leave=float(bal.available_leave) if bal else 0.0,
        last_updated=bal.updated_at if bal else None,
    )


# ---------- manager: edit ---------------------------------------------------

def _fmt(value: Decimal | None) -> str:
    """Render a balance for display: '12.5', '-2', '0' (no trailing zeros)."""
    if value is None:
        return "0"
    return f"{float(value):g}"


def _notify_balance_change(
    db: Session,
    user_id: uuid.UUID,
    employee_id: uuid.UUID,
    old_value: Decimal | None,
    new_value: Decimal,
    reason: str,
) -> None:
    """In-app notification to the employee whose balance a manager changed."""
    from app.modules.notifications.service import create_notification

    new_txt = _fmt(new_value)
    if old_value is None:
        body = f"Your available leave was set to {new_txt}."
    else:
        body = f"Your available leave changed from {_fmt(old_value)} to {new_txt}."
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
    emp = _alive_employee(db, employee_id)
    new_value = Decimal(str(data.available_leave)).quantize(Decimal("0.01"))

    bal = db.execute(
        select(EmployeeLeaveBalance).where(
            EmployeeLeaveBalance.employee_id == emp.id
        )
    ).scalar_one_or_none()
    old_value = bal.available_leave if bal else None

    if bal is None:
        bal = EmployeeLeaveBalance(employee_id=emp.id, available_leave=new_value)
        db.add(bal)
    else:
        bal.available_leave = new_value
        db.add(bal)

    # Every change writes a history row — no exceptions.
    db.add(
        EmployeeLeaveBalanceHistory(
            employee_id=emp.id,
            old_balance=old_value,
            new_balance=new_value,
            reason=data.reason.strip(),
            updated_by=actor.id,
        )
    )

    # Let the employee know their balance changed (in-app notification). Only
    # on an actual value change, and only if they have a linked login account.
    # Emitted before commit so it's atomic with the balance + history rows.
    if old_value != new_value and emp.user_id is not None:
        _notify_balance_change(db, emp.user_id, emp.id, old_value, new_value, data.reason)

    db.commit()
    db.refresh(bal)
    return LeaveBalanceOut(
        employee_id=emp.id,
        employee_code=emp.employee_code,
        employee_name=emp.full_name,
        available_leave=float(bal.available_leave),
        last_updated=bal.updated_at,
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
