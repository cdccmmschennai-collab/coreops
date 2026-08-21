"""Production Status endpoints (Phase 1 - the minimum Phase 2 needs).

  GET  /projects/{project_id}/production-status          latest per revision+activity
  GET  /projects/{project_id}/production-status/history  full trail (filterable)
  POST /projects/{project_id}/production-status          append one update

No PATCH / PUT / DELETE by design: production status is append-only history, so
a correction is a new update, not an edit of an old one.

The project is always taken from the path - it is what the caller is authorized
against, and it is what the plant information is derived from. It is never
accepted in a request body.
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.production_status import service
from app.modules.production_status.schemas import (
    ProductionStatusCreate,
    ProductionStatusOut,
)
from app.modules.users.models import User

router = APIRouter(prefix="/projects", tags=["production-status"])


@router.get("/{project_id}/production-status", response_model=list[ProductionStatusOut])
def list_latest_production_status(
    project_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProductionStatusOut]:
    return service.list_latest(db, current, project_id)


@router.get(
    "/{project_id}/production-status/history",
    response_model=list[ProductionStatusOut],
)
def list_production_status_history(
    project_id: uuid.UUID,
    activity_id: uuid.UUID | None = Query(default=None),
    revision: str | None = Query(default=None),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProductionStatusOut]:
    return service.list_history(
        db, current, project_id, activity_id=activity_id, revision=revision
    )


@router.post(
    "/{project_id}/production-status",
    response_model=ProductionStatusOut,
    status_code=201,
)
def create_production_status(
    project_id: uuid.UUID,
    body: ProductionStatusCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProductionStatusOut:
    return service.create_production_status(db, current, project_id, body)
