"""Project activity endpoints.

  GET    /projects/{id}/activities
  POST   /projects/{id}/activities          PM only
  PATCH  /projects/{id}/activities/{aid}    PM + team_lead (team_lead: status/remarks only)
  DELETE /projects/{id}/activities/{aid}    PM only
"""
import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.project_activities import service
from app.modules.project_activities.schemas import (
    ProjectActivityCreate,
    ProjectActivityOut,
    ProjectActivityUpdate,
)
from app.modules.users.models import User

router = APIRouter(prefix="/projects", tags=["project-activities"])


@router.get("/{project_id}/activities", response_model=list[ProjectActivityOut])
def list_activities(
    project_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProjectActivityOut]:
    return [
        ProjectActivityOut.model_validate(a)
        for a in service.list_activities(db, current, project_id)
    ]


@router.post("/{project_id}/activities", response_model=ProjectActivityOut, status_code=201)
def create_activity(
    project_id: uuid.UUID,
    body: ProjectActivityCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectActivityOut:
    return ProjectActivityOut.model_validate(
        service.create_activity(db, current, project_id, body)
    )


@router.patch("/{project_id}/activities/{activity_id}", response_model=ProjectActivityOut)
def update_activity(
    project_id: uuid.UUID,
    activity_id: uuid.UUID,
    body: ProjectActivityUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectActivityOut:
    return ProjectActivityOut.model_validate(
        service.update_activity(db, current, project_id, activity_id, body)
    )


@router.delete("/{project_id}/activities/{activity_id}", status_code=204)
def delete_activity(
    project_id: uuid.UUID,
    activity_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    service.delete_activity(db, current, project_id, activity_id)
    return Response(status_code=204)
