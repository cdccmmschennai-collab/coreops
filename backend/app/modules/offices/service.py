"""Office service — admin-only CRUD.

RBAC: all endpoints require admin role (enforced at the router level).
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.offices.models import Office
from app.modules.offices.schemas import OfficeCreate, OfficeUpdate
from app.shared.errors import AppError


def _fetch(db: Session, office_id: uuid.UUID) -> Office:
    office = db.get(Office, office_id)
    if office is None:
        raise AppError("not_found", "Office not found.", 404)
    return office


def list_offices(
    db: Session,
    *,
    limit: int,
    offset: int,
) -> tuple[list[Office], int]:
    stmt = select(Office).order_by(Office.name)
    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    return list(rows), total


def get_office(db: Session, office_id: uuid.UUID) -> Office:
    return _fetch(db, office_id)


def create_office(db: Session, data: OfficeCreate) -> Office:
    office = Office(**data.model_dump())
    db.add(office)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "An office with this name already exists.", 409)
    db.refresh(office)
    return office


def update_office(db: Session, office_id: uuid.UUID, data: OfficeUpdate) -> Office:
    office = _fetch(db, office_id)
    fields = data.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(office, key, value)
    db.add(office)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "An office with this name already exists.", 409)
    db.refresh(office)
    return office
