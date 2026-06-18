"""Task endpoints.

  GET    /tasks              list (RBAC-scoped) + filters/pagination
  POST   /tasks              create (project_manager)
  GET    /tasks/{id}         read (RBAC-scoped)
  PATCH  /tasks/{id}         update (project_manager)
  PATCH  /tasks/{id}/status  update status (assignee employee)
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.tasks import service
from app.modules.tasks.models import TaskPriority, TaskStatus
from app.modules.tasks.schemas import (
    AssignableProject,
    TaskCreate,
    TaskOut,
    TaskPage,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.modules.users.models import User

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=TaskPage)
def list_tasks(
    mine: bool = Query(default=False),
    q: str | None = Query(default=None),
    status: TaskStatus | None = Query(default=None),
    priority: TaskPriority | None = Query(default=None),
    due_from: date | None = Query(default=None, alias="due_from"),
    due_to: date | None = Query(default=None, alias="due_to"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskPage:
    rows, total = service.list_tasks(
        db,
        current,
        mine=mine,
        q=q,
        status=status,
        priority=priority,
        due_from=due_from,
        due_to=due_to,
        limit=limit,
        offset=offset,
    )
    return TaskPage(
        items=[TaskOut.from_task(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=TaskOut, status_code=201)
def create_task(
    body: TaskCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskOut:
    # Authorization (project_manager, or team lead of the target project) is
    # enforced inside the service.
    return TaskOut.from_task(service.create_task(db, current, body))


@router.get("/assignable-projects", response_model=list[AssignableProject])
def assignable_projects(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AssignableProject]:
    """Projects the current user leads + the members they may assign to."""
    return service.list_assignable_projects(db, current)


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskOut:
    return TaskOut.from_task(service.get_task(db, current, task_id))


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskOut:
    # PM may fully edit; the assigner (team lead) may only cancel — enforced in
    # the service.
    return TaskOut.from_task(service.update_task(db, current, task_id, body))


@router.patch("/{task_id}/status", response_model=TaskOut)
def update_task_status(
    task_id: uuid.UUID,
    body: TaskStatusUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskOut:
    return TaskOut.from_task(service.update_task_status(db, current, task_id, body))
