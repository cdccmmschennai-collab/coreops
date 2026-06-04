"""ActivityType endpoints.

  GET    /activity-types             list (public — all authenticated roles)
  POST   /activity-types             create (admin only)
  GET    /activity-types/{id}        get one (public)
  PATCH  /activity-types/{id}        update (admin only)
  DELETE /activity-types/{id}        soft-deactivate (admin only)
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.modules.activity_types import service
from app.modules.activity_types.schemas import (
    ActivityTypeCreate,
    ActivityTypeOut,
    ActivityTypePage,
    ActivityTypeUpdate,
)
from app.modules.users.models import User

router = APIRouter(prefix="/activity-types", tags=["activity-types"])

AdminUser = Depends(require_role("project_manager"))
AuthUser = Depends(get_current_user)


@router.get("", response_model=ActivityTypePage)
def list_activity_types(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    category: str | None = Query(default=None),
    requires_project: bool | None = Query(default=None),
    active_only: bool = Query(default=True),
    _user: User = AuthUser,
    db: Session = Depends(get_db),
) -> ActivityTypePage:
    rows, total = service.list_activity_types(
        db,
        limit=limit,
        offset=offset,
        category=category,
        requires_project=requires_project,
        active_only=active_only,
    )
    return ActivityTypePage(
        items=[ActivityTypeOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=ActivityTypeOut, status_code=201)
def create_activity_type(
    body: ActivityTypeCreate,
    admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> ActivityTypeOut:
    return ActivityTypeOut.model_validate(
        service.create_activity_type(db, body, created_by=admin.id)
    )


@router.get("/{activity_type_id}", response_model=ActivityTypeOut)
def get_activity_type(
    activity_type_id: uuid.UUID,
    _user: User = AuthUser,
    db: Session = Depends(get_db),
) -> ActivityTypeOut:
    return ActivityTypeOut.model_validate(service.get_activity_type(db, activity_type_id))


@router.patch("/{activity_type_id}", response_model=ActivityTypeOut)
def update_activity_type(
    activity_type_id: uuid.UUID,
    body: ActivityTypeUpdate,
    _admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> ActivityTypeOut:
    return ActivityTypeOut.model_validate(
        service.update_activity_type(db, activity_type_id, body)
    )


@router.delete("/{activity_type_id}", response_model=ActivityTypeOut)
def deactivate_activity_type(
    activity_type_id: uuid.UUID,
    _admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> ActivityTypeOut:
    return ActivityTypeOut.model_validate(
        service.deactivate_activity_type(db, activity_type_id)
    )
