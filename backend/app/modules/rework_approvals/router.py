"""Rework Activity Approval endpoints (Phase 3).

  GET  /rework-approvals                    PM listing (filters, 10/page, counts)
  GET  /rework-approvals/pending-count      PM home-card count
  GET  /rework-approvals/filter-options     PM dropdown sources
  GET  /rework-approvals/{id}               detail (PM, or the owning employee)
  POST /rework-approvals/{id}/approve       PM, remarks optional
  POST /rework-approvals/{id}/reject        PM, remarks REQUIRED
  POST /rework-approvals/{id}/correct       employee: replace the rejected row
                                            and resubmit it (new cycle)

Every authorization rule is enforced in service.py; an email link grants
nothing on its own - all routes require an authenticated session.
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.rework_approvals import service
from app.modules.rework_approvals.schemas import (
    ReworkDecisionIn,
    ReworkFilterOptions,
    ReworkRequestDetailOut,
    ReworkRequestPage,
    ReworkStatus,
)
from app.modules.users.models import User
from app.modules.work_reports.schemas import WorkReportOut, WorkReportTaskIn

router = APIRouter(prefix="/rework-approvals", tags=["rework-approvals"])


@router.get("", response_model=ReworkRequestPage)
def list_rework_requests(
    status: ReworkStatus | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    employee_id: uuid.UUID | None = Query(default=None),
    report_date: date | None = Query(default=None),
    sub_activity_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReworkRequestPage:
    return ReworkRequestPage.model_validate(
        service.list_requests(
            db, user,
            status=status, project_id=project_id, employee_id=employee_id,
            report_date=report_date, sub_activity_id=sub_activity_id,
            limit=limit, offset=offset,
        )
    )


@router.get("/pending-count")
def rework_pending_count(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return {"count": service.pending_count(db, user)}


@router.get("/filter-options", response_model=ReworkFilterOptions)
def rework_filter_options(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ReworkFilterOptions:
    return ReworkFilterOptions.model_validate(service.filter_options(db, user))


@router.get("/{request_id}", response_model=ReworkRequestDetailOut)
def get_rework_request(
    request_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReworkRequestDetailOut:
    return ReworkRequestDetailOut.model_validate(service.get_request(db, user, request_id))


@router.post("/{request_id}/approve", response_model=ReworkRequestDetailOut)
def approve_rework_request(
    request_id: uuid.UUID,
    body: ReworkDecisionIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReworkRequestDetailOut:
    return ReworkRequestDetailOut.model_validate(
        service.approve_request(db, user, request_id, body.remarks)
    )


@router.post("/{request_id}/correct", response_model=WorkReportOut)
def correct_rework_request(
    request_id: uuid.UUID,
    body: WorkReportTaskIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkReportOut:
    """Employee: replace the rejected row and resubmit it (a new approval
    cycle). Only the rejected row changes; the report stays submitted."""
    from app.modules.work_reports import service as work_reports_service

    return WorkReportOut.model_validate(
        work_reports_service.correct_rejected_rework_row(db, user, request_id, body)
    )


@router.post("/{request_id}/reject", response_model=ReworkRequestDetailOut)
def reject_rework_request(
    request_id: uuid.UUID,
    body: ReworkDecisionIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReworkRequestDetailOut:
    return ReworkRequestDetailOut.model_validate(
        service.reject_request(db, user, request_id, body.remarks)
    )
