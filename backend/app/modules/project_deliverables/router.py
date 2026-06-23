"""Project deliverable endpoints.

  GET    /deliverables                                   list all (scoped)
  GET    /deliverables/{id}                              detail (member+)
  GET    /deliverables/{id}/changes                      change history (member+)
  GET    /projects/{project_id}/deliverables            list (member+)
  POST   /projects/{project_id}/deliverables            create (PM / team lead)
  PATCH  /projects/{project_id}/deliverables/{id}       update (PM / team lead)
  DELETE /projects/{project_id}/deliverables/{id}       delete (PM / team lead)
"""
import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.project_deliverables import service
from app.modules.project_deliverables.schemas import (
    DeliverableChangeOut,
    DeliverableCreate,
    DeliverableOut,
    DeliverableUpdate,
)
from app.modules.users.models import User

router = APIRouter(tags=["deliverables"])

_projects = APIRouter(prefix="/projects")
_global = APIRouter(prefix="/deliverables")


@_global.get("", response_model=list[DeliverableOut])
def list_all_deliverables(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DeliverableOut]:
    rows = service.list_all_deliverables(db, current)
    return [DeliverableOut.model_validate(r) for r in rows]


@_global.get("/{deliverable_id}", response_model=DeliverableOut)
def get_deliverable(
    deliverable_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeliverableOut:
    return DeliverableOut.model_validate(
        service.get_deliverable(db, current, deliverable_id)
    )


@_global.get("/{deliverable_id}/changes", response_model=list[DeliverableChangeOut])
def list_deliverable_changes(
    deliverable_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DeliverableChangeOut]:
    return [
        DeliverableChangeOut.model_validate(c)
        for c in service.list_deliverable_changes(db, current, deliverable_id)
    ]


@_projects.get("/{project_id}/deliverables", response_model=list[DeliverableOut])
def list_deliverables(
    project_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DeliverableOut]:
    rows = service.list_deliverables(db, current, project_id)
    return [DeliverableOut.model_validate(r) for r in rows]


@_projects.post(
    "/{project_id}/deliverables",
    response_model=DeliverableOut,
    status_code=201,
)
def create_deliverable(
    project_id: uuid.UUID,
    body: DeliverableCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeliverableOut:
    return DeliverableOut.model_validate(
        service.create_deliverable(db, current, project_id, body)
    )


@_projects.patch(
    "/{project_id}/deliverables/{deliverable_id}",
    response_model=DeliverableOut,
)
def update_deliverable(
    project_id: uuid.UUID,
    deliverable_id: uuid.UUID,
    body: DeliverableUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeliverableOut:
    return DeliverableOut.model_validate(
        service.update_deliverable(db, current, project_id, deliverable_id, body)
    )


@_projects.delete(
    "/{project_id}/deliverables/{deliverable_id}",
    status_code=204,
)
def delete_deliverable(
    project_id: uuid.UUID,
    deliverable_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    service.delete_deliverable(db, current, project_id, deliverable_id)
    return Response(status_code=204)


router.include_router(_projects)
router.include_router(_global)
