"""Daily Work Report endpoints (mirrors employees/projects/attendance routers).

  GET    /work-reports                 list (RBAC-scoped) + filters/pagination
  POST   /work-reports                 create draft  (report.submit: author)
  GET    /work-reports/{id}            read (RBAC-scoped)
  PATCH  /work-reports/{id}            edit draft/rejected (author)
  POST   /work-reports/{id}/submit     submit for review (author)
  POST   /work-reports/{id}/approve    approve (report.review: admin/owning manager)
  POST   /work-reports/{id}/reject     reject + note (report.review)
  DELETE /work-reports/{id}            delete own draft (author)

Coarse role gate at the router (the service enforces ownership + team scope):
  report.submit = admin, manager, employee   (write/own actions; viewer blocked)
  report.review = admin, manager             (approve/reject)
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.modules.users.models import User
from app.modules.work_reports import service
from app.modules.work_reports.models import WorkReportStatus
from app.modules.work_reports.schemas import (
    WorkReportCreate,
    WorkReportOut,
    WorkReportPage,
    WorkReportReject,
    WorkReportUpdate,
)

router = APIRouter(prefix="/work-reports", tags=["work-reports"])

# Capability gates (USER_ROLES → DWR capabilities, see spec §3).
require_submit = require_role("project_manager", "employee")
require_review = require_role("project_manager")


@router.get("", response_model=WorkReportPage)
def list_work_reports(
    employee_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    status: WorkReportStatus | None = Query(default=None),
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


@router.post("/{report_id}/approve", response_model=WorkReportOut)
def approve_work_report(
    report_id: uuid.UUID,
    current: User = Depends(require_review),
    db: Session = Depends(get_db),
) -> WorkReportOut:
    return WorkReportOut.model_validate(service.approve_work_report(db, current, report_id))


@router.post("/{report_id}/reject", response_model=WorkReportOut)
def reject_work_report(
    report_id: uuid.UUID,
    body: WorkReportReject,
    current: User = Depends(require_review),
    db: Session = Depends(get_db),
) -> WorkReportOut:
    return WorkReportOut.model_validate(
        service.reject_work_report(db, current, report_id, body)
    )


@router.delete("/{report_id}", status_code=204)
def delete_work_report(
    report_id: uuid.UUID,
    current: User = Depends(require_submit),
    db: Session = Depends(get_db),
) -> Response:
    service.delete_work_report(db, current, report_id)
    return Response(status_code=204)
