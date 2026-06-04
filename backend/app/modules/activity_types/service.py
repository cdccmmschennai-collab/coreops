"""ActivityType service — admin CRUD + public read."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.activity_types.models import ActivityType, VALID_CATEGORIES
from app.modules.activity_types.schemas import ActivityTypeCreate, ActivityTypeUpdate
from app.shared.errors import AppError


def _fetch(db: Session, activity_type_id: uuid.UUID) -> ActivityType:
    row = db.get(ActivityType, activity_type_id)
    if row is None:
        raise AppError("not_found", "Activity type not found.", 404)
    return row


def list_activity_types(
    db: Session,
    *,
    limit: int,
    offset: int,
    category: str | None = None,
    requires_project: bool | None = None,
    active_only: bool = True,
) -> tuple[list[ActivityType], int]:
    stmt = select(ActivityType)
    if active_only:
        stmt = stmt.where(ActivityType.is_active.is_(True))
    if category is not None:
        if category not in VALID_CATEGORIES:
            raise AppError("bad_request", f"Invalid category. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}.", 400)
        stmt = stmt.where(ActivityType.category == category)
    if requires_project is not None:
        stmt = stmt.where(ActivityType.requires_project.is_(requires_project))
    stmt = stmt.order_by(ActivityType.code.nulls_last(), ActivityType.name)
    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    return list(rows), total


def get_activity_type(db: Session, activity_type_id: uuid.UUID) -> ActivityType:
    return _fetch(db, activity_type_id)


def create_activity_type(
    db: Session, data: ActivityTypeCreate, *, created_by: uuid.UUID | None = None
) -> ActivityType:
    if data.category not in VALID_CATEGORIES:
        raise AppError("bad_request", f"Invalid category.", 400)
    row = ActivityType(**data.model_dump(), created_by=created_by)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "An active activity type with this code already exists.", 409)
    db.refresh(row)
    return row


def update_activity_type(
    db: Session, activity_type_id: uuid.UUID, data: ActivityTypeUpdate
) -> ActivityType:
    row = _fetch(db, activity_type_id)
    fields = data.model_dump(exclude_unset=True)
    if "category" in fields and fields["category"] not in VALID_CATEGORIES:
        raise AppError("bad_request", "Invalid category.", 400)
    for key, value in fields.items():
        setattr(row, key, value)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "An active activity type with this code already exists.", 409)
    db.refresh(row)
    return row


def deactivate_activity_type(db: Session, activity_type_id: uuid.UUID) -> ActivityType:
    row = _fetch(db, activity_type_id)
    row.is_active = False
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
