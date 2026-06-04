"""User administration service (project_manager only). Includes last-PM guards."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
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
) -> tuple[list[User], int]:
    stmt = select(User).where(User.deleted_at.is_(None))
    if q:
        stmt = stmt.where(User.email.ilike(f"%{q}%"))
    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def create_user(db: Session, data: UserCreate) -> User:
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
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session, user_id: uuid.UUID, data: UserUpdate, acting_user: User
) -> User:
    user = get_user(db, user_id)

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
    db.commit()
    db.refresh(user)
    return user


def set_role(
    db: Session, user_id: uuid.UUID, role: UserRole, acting_user: User
) -> User:
    return update_user(db, user_id, UserUpdate(role=role), acting_user)


def set_password(db: Session, user_id: uuid.UUID, new_password: str) -> None:
    user = get_user(db, user_id)
    try:
        user.password_hash = hash_password(new_password)
    except ValueError as exc:
        raise AppError("validation_error", str(exc), 422)
    db.add(user)
    db.commit()
