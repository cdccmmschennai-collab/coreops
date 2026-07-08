"""Daily Work Report endpoints (mirrors employees/projects/attendance routers).

  GET    /work-reports                  list (RBAC-scoped) + filters/pagination
  POST   /work-reports                  create draft  (author)
  GET    /work-reports/{id}             read (RBAC-scoped)
  PATCH  /work-reports/{id}             edit draft/rejected (author)
  POST   /work-reports/{id}/submit      submit (author)
  POST   /work-reports/{id}/request-edit  author asks the Project Head to reopen
  POST   /work-reports/{id}/grant-edit  Project Head reopens report for editing
  DELETE /work-reports/{id}             delete own draft (author)
  PATCH  /work-reports/tasks/{task_id}/completion
                                         toggle a TASK_BASED row's completion
                                         checkbox — author-only, works
                                         regardless of the parent report's
                                         status (see service docstring)

There is no approval step: a submitted report is final unless the Project Head
grants an edit request, which returns it to the editable 'granted' state.

Coarse role gate at the router; the service enforces the fine-grained rules:
  - author actions (create/edit/submit/request-edit/delete) → own reports
  - grant-edit → the Project Head of the report's projects (never the PM)
Both author and Head actions are reachable by project_manager + employee at the
router, so a Head (who is an employee) can reach the grant-edit endpoint.
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.modules.users.models import User
from app.modules.work_reports import service
from app.modules.work_reports.schemas import (
    TaskCompletionUpdate,
    WorkReportCreate,
    WorkReportEditRequest,
    WorkReportOut,
    WorkReportPage,
    WorkReportStatusFilter,
    WorkReportTaskOut,
    WorkReportUpdate,
)

router = APIRouter(prefix="/work-reports", tags=["work-reports"])

# Capability gate (USER_ROLES → DWR capabilities, see spec §3).
require_submit = require_role("project_manager", "employee")


@router.get("", response_model=WorkReportPage)
def list_work_reports(
    employee_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    status: WorkReportStatusFilter | None = Query(default=None),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkReportPage:
    rows, total = service.list_work_reports(
        db,
        current,
        employee_id=employee_id,
        project_id=project_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return WorkReportPage(
        items=[WorkReportOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=WorkReportOut, status_code=201)
def create_work_report(
    body: WorkReportCreate,
    current: User = Depends(require_submit),
    db: Session = Depends(get_db),
) -> WorkReportOut:
    return WorkReportOut.model_validate(service.create_work_report(db, current, body))


@router.get("/{report_id}", response_model=WorkReportOut)
def get_work_report(
    report_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkReportOut:
    return WorkReportOut.model_validate(service.get_work_report(db, current, report_id))


@router.patch("/{report_id}", response_model=WorkReportOut)
def update_work_report(
    report_id: uuid.UUID,
    body: WorkReportUpdate,
    current: User = Depends(require_submit),
    db: Session = Depends(get_db),
) -> WorkReportOut:
    return WorkReportOut.model_validate(
        service.update_work_report(db, current, report_id, body)
    )


@router.post("/{report_id}/submit", response_model=WorkReportOut)
def submit_work_report(
    report_id: uuid.UUID,
    current: User = Depends(require_submit),
    db: Session = Depends(get_db),
) -> WorkReportOut:
    return WorkReportOut.model_validate(service.submit_work_report(db, current, report_id))


@router.post("/{report_id}/request-edit", response_model=WorkReportOut)
def request_edit_work_report(
    report_id: uuid.UUID,
    body: WorkReportEditRequest,
    current: User = Depends(require_submit),
    db: Session = Depends(get_db),
) -> WorkReportOut:
    return WorkReportOut.model_validate(
        service.request_edit_work_report(db, current, report_id, body)
    )


@router.post("/{report_id}/grant-edit", response_model=WorkReportOut)
def grant_edit_work_report(
    report_id: uuid.UUID,
    current: User = Depends(require_submit),
    db: Session = Depends(get_db),
) -> WorkReportOut:
    return WorkReportOut.model_validate(
        service.grant_edit_work_report(db, current, report_id)
    )


@router.delete("/{report_id}", status_code=204)
def delete_work_report(
    report_id: uuid.UUID,
    current: User = Depends(require_submit),
    db: Session = Depends(get_db),
) -> Response:
    service.delete_work_report(db, current, report_id)
    return Response(status_code=204)


@router.patch("/tasks/{task_id}/completion", response_model=WorkReportTaskOut)
def update_task_completion(
    task_id: uuid.UUID,
    body: TaskCompletionUpdate,
    current: User = Depends(require_submit),
    db: Session = Depends(get_db),
) -> WorkReportTaskOut:
    return WorkReportTaskOut.model_validate(
        service.update_task_completion(db, current, task_id, body)
    )
