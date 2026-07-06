"""Project endpoints (mirrors employees/router.py).

  GET    /projects                                   list (RBAC-scoped) + search/filter/pagination
  POST   /projects                                   create (admin)
  GET    /projects/{id}                              read (RBAC-scoped)
  PATCH  /projects/{id}                              update (admin)
  DELETE /projects/{id}                              archive / soft-delete (admin)
  GET    /projects/{id}/members                      list members (RBAC-scoped)
  POST   /projects/{id}/members                      assign employee (admin)
  PATCH  /projects/{id}/members/{employee_id}        change member role (admin)
  DELETE /projects/{id}/members/{employee_id}        unassign (admin)
"""
import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.modules.projects import service
from app.modules.projects.models import ProjectStatus
from app.modules.projects.schemas import (
    LedProject,
    PlannedDateChangeOut,
    PlannedDateUpdate,
    ProjectCreate,
    ProjectHeadUpdate,
    ProjectMemberCreate,
    ProjectMemberOut,
    ProjectMemberRoleUpdate,
    ProjectOut,
    ProjectPage,
    ProjectUpdate,
    TimelineEventOut,
)
from app.modules.users.models import User

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ProjectPage)
def list_projects(
    q: str | None = Query(default=None),
    status: ProjectStatus | None = Query(default=None),
    employee_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectPage:
    rows, total = service.list_projects(
        db, current, q=q, status=status, employee_id=employee_id, limit=limit, offset=offset
    )
    return ProjectPage(
        items=[ProjectOut.model_validate(p) for p in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    body: ProjectCreate,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> ProjectOut:
    return ProjectOut.model_validate(service.create_project(db, admin, body))


@router.get("/led", response_model=list[LedProject])
def led_projects(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LedProject]:
    return service.list_led_projects(db, current)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectOut:
    return ProjectOut.model_validate(service.get_project(db, current, project_id))


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> ProjectOut:
    return ProjectOut.model_validate(service.update_project(db, admin, project_id, body))


@router.put("/{project_id}/head", response_model=ProjectOut)
def set_project_head(
    project_id: uuid.UUID,
    body: ProjectHeadUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectOut:
    # Authorization (PM only) is enforced centrally in the service via authz.
    return ProjectOut.model_validate(
        service.set_project_head(db, current, project_id, body.head_employee_id)
    )


@router.delete("/{project_id}", status_code=204)
def archive_project(
    project_id: uuid.UUID,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> Response:
    service.archive_project(db, admin, project_id)
    return Response(status_code=204)


@router.patch("/{project_id}/planned-completion-date", response_model=ProjectOut)
def update_planned_completion_date(
    project_id: uuid.UUID,
    body: PlannedDateUpdate,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> ProjectOut:
    return ProjectOut.model_validate(
        service.update_planned_completion_date(db, admin, project_id, body)
    )


@router.get("/{project_id}/timeline", response_model=list[TimelineEventOut])
def list_timeline(
    project_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TimelineEventOut]:
    return [
        TimelineEventOut.model_validate(e)
        for e in service.list_timeline(db, current, project_id)
    ]


@router.get("/{project_id}/planned-date-changes", response_model=list[PlannedDateChangeOut])
def list_planned_date_changes(
    project_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PlannedDateChangeOut]:
    return [
        PlannedDateChangeOut.model_validate(c)
        for c in service.list_planned_date_changes(db, current, project_id)
    ]


@router.get("/{project_id}/members", response_model=list[ProjectMemberOut])
def list_members(
    project_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProjectMemberOut]:
    return [
        ProjectMemberOut.model_validate(m)
        for m in service.list_members(db, current, project_id)
    ]


@router.post("/{project_id}/members", response_model=ProjectMemberOut, status_code=201)
def assign_member(
    project_id: uuid.UUID,
    body: ProjectMemberCreate,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> ProjectMemberOut:
    return ProjectMemberOut.model_validate(
        service.add_member(db, admin, project_id, body.employee_id, body.role)
    )


@router.patch(
    "/{project_id}/members/{employee_id}", response_model=ProjectMemberOut
)
def update_member_role(
    project_id: uuid.UUID,
    employee_id: uuid.UUID,
    body: ProjectMemberRoleUpdate,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> ProjectMemberOut:
    return ProjectMemberOut.model_validate(
        service.update_member_role(db, admin, project_id, employee_id, body.role)
    )


@router.delete("/{project_id}/members/{employee_id}", status_code=204)
def unassign_member(
    project_id: uuid.UUID,
    employee_id: uuid.UUID,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> Response:
    service.remove_member(db, admin, project_id, employee_id)
    return Response(status_code=204)
