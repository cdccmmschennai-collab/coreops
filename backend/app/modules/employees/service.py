"""Employee service: RBAC-scoped reads + project_manager writes.

RBAC (this module):
  project_manager  full access
  employee         read access, own record only
"""
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.audit import service as audit
from app.modules.audit.constants import AuditAction, EntityType
from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.employees.schemas import (
    AccountCreate,
    AccountLink,
    AccountPasswordReset,
    AccountRoleUpdate,
    AccountStatusUpdate,
    EmployeeCreate,
    EmployeeProfile,
    EmployeeUpdate,
)
from app.modules.offices.models import Office
from app.modules.users.models import User, UserRole
from app.shared.errors import AppError


def _current_employee(db: Session, user: User) -> Employee | None:
    return db.execute(
        select(Employee).where(Employee.user_id == user.id, Employee.deleted_at.is_(None))
    ).scalar_one_or_none()


def _alive():
    return select(Employee).where(Employee.deleted_at.is_(None))


def build_profile(db: Session, emp: Employee) -> EmployeeProfile:
    """Serialize an employee's business identity with manager/office names
    resolved server-side (the caller may not have read access to those rows)."""
    manager_name: str | None = None
    if emp.manager_id is not None:
        mgr = db.get(Employee, emp.manager_id)
        if mgr is not None and mgr.deleted_at is None:
            manager_name = mgr.full_name

    office_name: str | None = None
    if emp.office_id is not None:
        office = db.get(Office, emp.office_id)
        if office is not None:
            office_name = office.name

    return EmployeeProfile(
        id=emp.id,
        employee_code=emp.employee_code,
        first_name=emp.first_name,
        last_name=emp.last_name,
        full_name=emp.full_name,
        work_email=emp.work_email,
        personal_email=emp.personal_email,
        phone=emp.phone,
        department=emp.department,
        designation=emp.designation,
        manager_id=emp.manager_id,
        manager_name=manager_name,
        office_id=emp.office_id,
        office_name=office_name,
        date_of_joining=emp.date_of_joining,
        status=emp.status,
    )


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
    exclude_activity_id: uuid.UUID | None = None,
) -> tuple[list[Employee], int]:
    stmt = _alive()

    if actor.role == UserRole.employee:
        stmt = stmt.where(Employee.user_id == actor.id)
    # project_manager: no extra scope — full access

    if exclude_activity_id is not None:
        # Grant-picker helper (activity access control): drop employees who
        # already hold an active grant on this activity, so the search only
        # offers new candidates. NOT EXISTS keeps it a single indexed query.
        from sqlalchemy import exists

        from app.modules.activity_master.access_models import EmployeeActivityAccess

        stmt = stmt.where(
            ~exists(
                select(EmployeeActivityAccess.id).where(
                    EmployeeActivityAccess.activity_id == exclude_activity_id,
                    EmployeeActivityAccess.employee_id == Employee.id,
                    EmployeeActivityAccess.is_active.is_(True),
                )
            )
        )

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
    if actor.role == UserRole.project_manager:
        return
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


def _validate_reporting_pm(db: Session, reporting_pm_id: uuid.UUID | None) -> None:
    """The reporting PM must be an active project-manager user account.

    NULL is allowed at this layer (the column is nullable and legacy/imported
    rows may not have one yet); the mandatory-when-active rule is enforced later.
    """
    if reporting_pm_id is None:
        return
    user = db.get(User, reporting_pm_id)
    if (
        user is None
        or user.deleted_at is not None
        or not user.is_active
        or user.role != UserRole.project_manager
    ):
        raise AppError(
            "validation_error",
            "Reporting PM must be an active project manager.",
            422,
        )


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
    _validate_reporting_pm(db, data.reporting_pm_id)

    emp = Employee(**data.model_dump(), created_by=actor.id, updated_by=actor.id)
    db.add(emp)
    try:
        db.flush()
        audit.record_audit(
            db,
            action=AuditAction.EMPLOYEE_CREATE,
            actor=actor,
            entity_type=EntityType.EMPLOYEE,
            entity_id=emp.id,
            details={"employee_code": data.employee_code},
        )
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
    if "reporting_pm_id" in fields:
        _validate_reporting_pm(db, fields["reporting_pm_id"])

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
    audit.record_audit(
        db,
        action=AuditAction.EMPLOYEE_UPDATE,
        actor=actor,
        entity_type=EntityType.EMPLOYEE,
        entity_id=emp.id,
        details={"changed_fields": sorted(fields.keys())},
    )
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
    audit.record_audit(
        db,
        action=AuditAction.EMPLOYEE_DEACTIVATE,
        actor=actor,
        entity_type=EntityType.EMPLOYEE,
        entity_id=emp.id,
    )
    db.commit()


def get_team(db: Session, actor: User, emp_id: uuid.UUID) -> list[Employee]:
    if actor.role != UserRole.project_manager:
        raise AppError("forbidden", "Not permitted.", 403)
    rows = (
        db.execute(_alive().where(Employee.manager_id == emp_id).order_by(Employee.first_name))
        .scalars()
        .all()
    )
    return list(rows)


def _fetch_linked_user(db: Session, emp: Employee) -> User:
    if emp.user_id is None:
        raise AppError("not_found", "This employee has no linked account.", 404)
    user = db.get(User, emp.user_id)
    if user is None or user.deleted_at is not None:
        raise AppError("not_found", "Linked user account not found.", 404)
    return user


def create_and_link_account(
    db: Session, actor: User, emp_id: uuid.UUID, data: AccountCreate
) -> User:
    emp = _fetch(db, emp_id)
    if emp.user_id is not None:
        raise AppError("conflict", "Employee already has a linked account.", 409)

    # Reuse the users service for consistent password hashing and email checks.
    from app.modules.users.service import create_user
    from app.modules.users.schemas import UserCreate

    user = create_user(db, UserCreate(email=data.email, password=data.password, role=data.role), actor)
    emp.user_id = user.id
    emp.updated_by = actor.id
    db.add(emp)
    audit.record_audit(
        db,
        action=AuditAction.EMPLOYEE_ACCOUNT_LINK,
        actor=actor,
        entity_type=EntityType.EMPLOYEE,
        entity_id=emp.id,
        details={"user_id": str(user.id), "email": data.email, "role": data.role.value},
    )
    db.commit()
    db.refresh(user)
    return user


def reset_account_password(
    db: Session, actor: User, emp_id: uuid.UUID, data: AccountPasswordReset
) -> None:
    emp = _fetch(db, emp_id)
    _fetch_linked_user(db, emp)  # ensure account exists
    from app.modules.users.service import set_password
    set_password(db, emp.user_id, data.new_password, actor)  # type: ignore[arg-type]


def update_account_status(
    db: Session, actor: User, emp_id: uuid.UUID, data: AccountStatusUpdate
) -> User:
    emp = _fetch(db, emp_id)
    user = _fetch_linked_user(db, emp)
    from app.modules.users.service import update_user
    from app.modules.users.schemas import UserUpdate
    return update_user(db, user.id, UserUpdate(is_active=data.is_active), actor)


def change_account_role(
    db: Session, actor: User, emp_id: uuid.UUID, data: AccountRoleUpdate
) -> User:
    emp = _fetch(db, emp_id)
    user = _fetch_linked_user(db, emp)
    # Reuse the users service so the self-role and last-active-PM guards apply.
    from app.modules.users.service import set_role
    return set_role(db, user.id, data.role, actor)


def relink_account(
    db: Session, actor: User, emp_id: uuid.UUID, data: AccountLink
) -> User:
    """Point the employee at a different existing user account (one-to-one)."""
    emp = _fetch(db, emp_id)

    user = db.get(User, data.user_id)
    if user is None or user.deleted_at is not None:
        raise AppError("validation_error", "Target user account not found.", 422)

    # Enforce the one-to-one link: the target must not belong to another employee.
    clash = db.execute(
        select(Employee).where(
            Employee.user_id == data.user_id,
            Employee.id != emp.id,
            Employee.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if clash is not None:
        raise AppError("conflict", "That user is already linked to another employee.", 409)

    emp.user_id = user.id
    emp.updated_by = actor.id
    db.add(emp)
    audit.record_audit(
        db,
        action=AuditAction.EMPLOYEE_ACCOUNT_RELINK,
        actor=actor,
        entity_type=EntityType.EMPLOYEE,
        entity_id=emp.id,
        details={"user_id": str(user.id)},
    )
    db.commit()
    db.refresh(user)
    return user


def unlink_account(db: Session, actor: User, emp_id: uuid.UUID) -> None:
    """Detach the linked account (keeps the user row; clears employee.user_id)."""
    emp = _fetch(db, emp_id)
    if emp.user_id is None:
        raise AppError("not_found", "This employee has no linked account.", 404)
    detached_user_id = emp.user_id
    emp.user_id = None
    emp.updated_by = actor.id
    db.add(emp)
    audit.record_audit(
        db,
        action=AuditAction.EMPLOYEE_ACCOUNT_UNLINK,
        actor=actor,
        entity_type=EntityType.EMPLOYEE,
        entity_id=emp.id,
        details={"user_id": str(detached_user_id)},
    )
    db.commit()
