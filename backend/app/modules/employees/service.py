"""Employee service: RBAC-scoped reads + admin writes.

RBAC (this module):
  admin    full access
  manager  read access, scoped to their team (employees where manager_id = self)
  employee read access, own record only
  viewer   read access, all
"""
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.employees.schemas import EmployeeCreate, EmployeeUpdate
from app.modules.offices.models import Office
from app.modules.users.models import User, UserRole
from app.shared.errors import AppError


def _current_employee(db: Session, user: User) -> Employee | None:
    return db.execute(
        select(Employee).where(Employee.user_id == user.id, Employee.deleted_at.is_(None))
    ).scalar_one_or_none()


def _alive():
    return select(Employee).where(Employee.deleted_at.is_(None))


def list_employees(
    db: Session,
    actor: User,
    *,
    q: str | None,
    status: EmployeeStatus | None,
    department: str | None,
    manager_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[Employee], int]:
    stmt = _alive()

    # Role scoping
    if actor.role == UserRole.employee:
        stmt = stmt.where(Employee.user_id == actor.id)
    elif actor.role == UserRole.manager:
        me = _current_employee(db, actor)
        if me is None:
            return [], 0
        stmt = stmt.where(Employee.manager_id == me.id)
    # admin / viewer: no extra scope

    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Employee.first_name.ilike(like),
                Employee.last_name.ilike(like),
                Employee.employee_code.ilike(like),
                Employee.work_email.ilike(like),
            )
        )
    if status is not None:
        stmt = stmt.where(Employee.status == status)
    if department:
        stmt = stmt.where(Employee.department.ilike(f"%{department}%"))
    if manager_id is not None:
        stmt = stmt.where(Employee.manager_id == manager_id)

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(stmt.order_by(Employee.created_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def _assert_can_read(db: Session, actor: User, emp: Employee) -> None:
    if actor.role in (UserRole.admin, UserRole.viewer):
        return
    if actor.role == UserRole.manager:
        me = _current_employee(db, actor)
        if me is not None and (emp.manager_id == me.id or emp.id == me.id):
            return
        raise AppError("forbidden", "You can only view your team.", 403)
    if actor.role == UserRole.employee:
        if emp.user_id == actor.id:
            return
        raise AppError("forbidden", "You can only view your own record.", 403)
    raise AppError("forbidden", "Not permitted.", 403)


def _fetch(db: Session, emp_id: uuid.UUID) -> Employee:
    emp = db.get(Employee, emp_id)
    if emp is None or emp.deleted_at is not None:
        raise AppError("not_found", "Employee not found.", 404)
    return emp


def get_employee(db: Session, actor: User, emp_id: uuid.UUID) -> Employee:
    emp = _fetch(db, emp_id)
    _assert_can_read(db, actor, emp)
    return emp


def _validate_manager(
    db: Session, manager_id: uuid.UUID | None, self_id: uuid.UUID | None = None
) -> None:
    if manager_id is None:
        return
    if self_id is not None and manager_id == self_id:
        raise AppError("validation_error", "An employee cannot be their own manager.", 422)
    mgr = db.get(Employee, manager_id)
    if mgr is None or mgr.deleted_at is not None:
        raise AppError("validation_error", "Manager not found.", 422)


def _validate_office(db: Session, office_id: uuid.UUID | None) -> None:
    if office_id is None:
        return
    office = db.get(Office, office_id)
    if office is None:
        raise AppError("validation_error", "Office not found.", 422)


def create_employee(db: Session, actor: User, data: EmployeeCreate) -> Employee:
    if db.execute(
        select(Employee).where(
            Employee.employee_code == data.employee_code, Employee.deleted_at.is_(None)
        )
    ).scalar_one_or_none():
        raise AppError("conflict", "An employee with this code already exists.", 409)

    if data.work_email and db.execute(
        select(Employee).where(
            Employee.work_email == data.work_email, Employee.deleted_at.is_(None)
        )
    ).scalar_one_or_none():
        raise AppError("conflict", "An employee with this work email already exists.", 409)

    if data.user_id is not None:
        user = db.get(User, data.user_id)
        if user is None or user.deleted_at is not None:
            raise AppError("validation_error", "Linked user not found.", 422)
        if db.execute(
            select(Employee).where(
                Employee.user_id == data.user_id, Employee.deleted_at.is_(None)
            )
        ).scalar_one_or_none():
            raise AppError("conflict", "This user is already linked to an employee.", 409)

    _validate_manager(db, data.manager_id)
    _validate_office(db, data.office_id)

    emp = Employee(**data.model_dump(), created_by=actor.id, updated_by=actor.id)
    db.add(emp)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "Employee violates a uniqueness constraint.", 409)
    db.refresh(emp)
    return emp


def update_employee(
    db: Session, actor: User, emp_id: uuid.UUID, data: EmployeeUpdate
) -> Employee:
    emp = _fetch(db, emp_id)
    fields = data.model_dump(exclude_unset=True)

    if "manager_id" in fields:
        _validate_manager(db, fields["manager_id"], self_id=emp.id)
    if "office_id" in fields:
        _validate_office(db, fields["office_id"])

    if fields.get("work_email"):
        clash = db.execute(
            select(Employee).where(
                Employee.work_email == fields["work_email"],
                Employee.id != emp.id,
                Employee.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if clash:
            raise AppError("conflict", "An employee with this work email already exists.", 409)

    for key, value in fields.items():
        setattr(emp, key, value)
    emp.updated_by = actor.id
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


def deactivate_employee(db: Session, actor: User, emp_id: uuid.UUID) -> None:
    from datetime import datetime, timezone

    emp = _fetch(db, emp_id)
    emp.status = EmployeeStatus.exited
    emp.deleted_at = datetime.now(timezone.utc)
    emp.updated_by = actor.id
    db.add(emp)
    db.commit()


def get_team(db: Session, actor: User, emp_id: uuid.UUID) -> list[Employee]:
    if actor.role == UserRole.manager:
        me = _current_employee(db, actor)
        if me is None or me.id != emp_id:
            raise AppError("forbidden", "You can only view your own team.", 403)
    elif actor.role != UserRole.admin:
        raise AppError("forbidden", "Not permitted.", 403)

    rows = (
        db.execute(_alive().where(Employee.manager_id == emp_id).order_by(Employee.first_name))
        .scalars()
        .all()
    )
    return list(rows)
