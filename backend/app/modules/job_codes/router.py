"""JobCode endpoints.

  GET    /job-codes             list (public — all authenticated roles)
  POST   /job-codes             create (admin only)
  GET    /job-codes/{id}        get one (public)
  PATCH  /job-codes/{id}        update (admin only)
  DELETE /job-codes/{id}        soft-deactivate (admin only)
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.modules.job_codes import service
from app.modules.job_codes.schemas import (
    JobCodeCreate,
    JobCodeOut,
    JobCodePage,
    JobCodeUpdate,
)
from app.modules.users.models import User

router = APIRouter(prefix="/job-codes", tags=["job-codes"])

AdminUser = Depends(require_role("project_manager"))
AuthUser = Depends(get_current_user)


@router.get("", response_model=JobCodePage)
def list_job_codes(
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    active_only: bool = Query(default=True),
    _user: User = AuthUser,
    db: Session = Depends(get_db),
) -> JobCodePage:
    rows, total = service.list_job_codes(db, limit=limit, offset=offset, active_only=active_only)
    return JobCodePage(
        items=[JobCodeOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=JobCodeOut, status_code=201)
def create_job_code(
    body: JobCodeCreate,
    admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> JobCodeOut:
    return JobCodeOut.model_validate(service.create_job_code(db, body, created_by=admin.id))


@router.get("/{job_code_id}", response_model=JobCodeOut)
def get_job_code(
    job_code_id: uuid.UUID,
    _user: User = AuthUser,
    db: Session = Depends(get_db),
) -> JobCodeOut:
    return JobCodeOut.model_validate(service.get_job_code(db, job_code_id))


@router.patch("/{job_code_id}", response_model=JobCodeOut)
def update_job_code(
    job_code_id: uuid.UUID,
    body: JobCodeUpdate,
    _admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> JobCodeOut:
    return JobCodeOut.model_validate(service.update_job_code(db, job_code_id, body))


@router.delete("/{job_code_id}", response_model=JobCodeOut)
def deactivate_job_code(
    job_code_id: uuid.UUID,
    _admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> JobCodeOut:
    return JobCodeOut.model_validate(service.deactivate_job_code(db, job_code_id))
