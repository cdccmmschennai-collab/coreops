"""User administration service (project_manager only). Includes last-PM guards."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.modules.audit import service as audit
from app.modules.audit.constants import AuditAction, EntityType
from app.modules.employees.models import Employee
from app.modules.users.models import User, UserRole
from app.modules.users.schemas import UserCreate, UserUpdate
from app.shared.errors import AppError


def _active_pm_count(db: Session) -> int:
    return db.execute(
        select(func.count())
        .select_from(User)
        .where(
            User.role == UserRole.project_manager,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    ).scalar_one()


def _guard_not_last_pm(db: Session, user: User) -> None:
    if user.role == UserRole.project_manager and _active_pm_count(db) <= 1:
        raise AppError("conflict", "Cannot remove the last active project manager.", 409)


def get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise AppError("not_found", "User not found.", 404)
    return user


def list_users(
    db: Session, q: str | None, limit: int, offset: int
) -> tuple[list[User], int, dict[uuid.UUID, Employee]]:
    stmt = select(User).where(User.deleted_at.is_(None))
    if q:
        stmt = stmt.where(User.email.ilike(f"%{q}%"))
    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = list(
        db.execute(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )

    # Attach the linked employee (one-to-one) for this page in a single query.
    emp_map: dict[uuid.UUID, Employee] = {}
    user_ids = [u.id for u in rows]
    if user_ids:
        emps = db.execute(
            select(Employee).where(
                Employee.user_id.in_(user_ids), Employee.deleted_at.is_(None)
            )
        ).scalars().all()
        emp_map = {e.user_id: e for e in emps if e.user_id is not None}

    return rows, total, emp_map


def create_user(db: Session, data: UserCreate, acting_user: User | None = None) -> User:
    exists = db.execute(
        select(User).where(User.email == data.email, User.deleted_at.is_(None))
    ).scalar_one_or_none()
    if exists is not None:
        raise AppError("conflict", "A user with this email already exists.", 409)
    try:
        pw_hash = hash_password(data.password)
    except ValueError as exc:
        raise AppError("validation_error", str(exc), 422)
    user = User(email=data.email, password_hash=pw_hash, role=data.role)
    db.add(user)
    db.flush()
    audit.record_audit(
        db,
        action=AuditAction.USER_CREATE,
        actor=acting_user,
        entity_type=EntityType.USER,
        entity_id=user.id,
        details={"email": data.email, "role": data.role.value},
    )
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session, user_id: uuid.UUID, data: UserUpdate, acting_user: User
) -> User:
    user = get_user(db, user_id)
    prev_is_active = user.is_active
    prev_role = user.role

    if data.is_active is not None and data.is_active is False:
        if user.id == acting_user.id:
            raise AppError("conflict", "You cannot deactivate yourself.", 409)
        _guard_not_last_pm(db, user)
        user.is_active = False
    elif data.is_active is True:
        user.is_active = True

    if data.role is not None and data.role != user.role:
        if user.id == acting_user.id and user.role == UserRole.project_manager:
            raise AppError("conflict", "You cannot change your own role.", 409)
        _guard_not_last_pm(db, user)
        user.role = data.role

    db.add(user)

    if user.is_active != prev_is_active:
        audit.record_audit(
            db,
            action=AuditAction.USER_STATUS_CHANGE,
            actor=acting_user,
            entity_type=EntityType.USER,
            entity_id=user.id,
            details={"from": prev_is_active, "to": user.is_active},
        )
    if user.role != prev_role:
        audit.record_audit(
            db,
            action=AuditAction.USER_ROLE_CHANGE,
            actor=acting_user,
            entity_type=EntityType.USER,
            entity_id=user.id,
            details={"from": prev_role.value, "to": user.role.value},
        )

    db.commit()
    db.refresh(user)
    return user


def set_role(
    db: Session, user_id: uuid.UUID, role: UserRole, acting_user: User
) -> User:
    return update_user(db, user_id, UserUpdate(role=role), acting_user)


def set_password(
    db: Session, user_id: uuid.UUID, new_password: str, acting_user: User | None = None
) -> None:
    user = get_user(db, user_id)
    try:
        user.password_hash = hash_password(new_password)
    except ValueError as exc:
        raise AppError("validation_error", str(exc), 422)
    db.add(user)
    audit.record_audit(
        db,
        action=AuditAction.USER_PASSWORD_RESET,
        actor=acting_user,
        entity_type=EntityType.USER,
        entity_id=user.id,
    )
    db.commit()
