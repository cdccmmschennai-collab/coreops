"""JobCode service — admin CRUD + public read."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.job_codes.models import JobCode
from app.modules.job_codes.schemas import JobCodeCreate, JobCodeUpdate
from app.shared.errors import AppError


def _fetch(db: Session, job_code_id: uuid.UUID) -> JobCode:
    row = db.get(JobCode, job_code_id)
    if row is None:
        raise AppError("not_found", "Job code not found.", 404)
    return row


def list_job_codes(
    db: Session,
    *,
    limit: int,
    offset: int,
    active_only: bool = True,
) -> tuple[list[JobCode], int]:
    stmt = select(JobCode)
    if active_only:
        stmt = stmt.where(JobCode.is_active.is_(True))
    stmt = stmt.order_by(JobCode.code)
    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    return list(rows), total


def get_job_code(db: Session, job_code_id: uuid.UUID) -> JobCode:
    return _fetch(db, job_code_id)


def create_job_code(
    db: Session, data: JobCodeCreate, *, created_by: uuid.UUID | None = None
) -> JobCode:
    row = JobCode(**data.model_dump(), created_by=created_by)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "An active job code with this code already exists.", 409)
    db.refresh(row)
    return row


def update_job_code(
    db: Session, job_code_id: uuid.UUID, data: JobCodeUpdate
) -> JobCode:
    row = _fetch(db, job_code_id)
    fields = data.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(row, key, value)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "An active job code with this code already exists.", 409)
    db.refresh(row)
    return row


def deactivate_job_code(db: Session, job_code_id: uuid.UUID) -> JobCode:
    row = _fetch(db, job_code_id)
    row.is_active = False
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
