"""Attendance endpoints (mirrors employees/projects routers).

  GET    /attendance                       list (RBAC-scoped) + filters/pagination
  POST   /attendance                       create (admin)
  GET    /attendance/{id}                   read (RBAC-scoped)
  PATCH  /attendance/{id}                   update (admin)
  DELETE /attendance/{id}                   delete (admin)
  GET    /employees/{employee_id}/attendance   list one employee's attendance (scoped)
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.modules.attendance import service
from app.modules.attendance.models import AttendanceStatus
from app.modules.attendance.schemas import (
    AttendanceBulkSave,
    AttendanceCreate,
    AttendanceOut,
    AttendancePage,
    AttendanceSheet,
    AttendanceSheetRow,
    AttendanceUpdate,
)
from app.modules.users.models import User

router = APIRouter(prefix="/attendance", tags=["attendance"])
employee_router = APIRouter(prefix="/employees", tags=["attendance"])


@router.get("", response_model=AttendancePage)
def list_attendance(
    employee_id: uuid.UUID | None = Query(default=None),
    status: AttendanceStatus | None = Query(default=None),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AttendancePage:
    rows, total = service.list_attendance(
        db,
        current,
        employee_id=employee_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return AttendancePage(
        items=[AttendanceOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=AttendanceOut, status_code=201)
def create_attendance(
    body: AttendanceCreate,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> AttendanceOut:
    return AttendanceOut.model_validate(service.create_attendance(db, admin, body))


@router.get("/sheet", response_model=AttendanceSheet)
def get_attendance_sheet(
    date: date = Query(...),
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> AttendanceSheet:
    rows, exists = service.get_attendance_sheet(db, admin, date)
    return AttendanceSheet(
        attendance_date=date,
        exists=exists,
        rows=[AttendanceSheetRow.model_validate(r) for r in rows],
    )


@router.post("/bulk", response_model=AttendanceSheet)
def bulk_save_attendance(
    body: AttendanceBulkSave,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> AttendanceSheet:
    service.bulk_save_attendance(db, admin, body.date, body.records)
    rows, exists = service.get_attendance_sheet(db, admin, body.date)
    return AttendanceSheet(
        attendance_date=body.date,
        exists=exists,
        rows=[AttendanceSheetRow.model_validate(r) for r in rows],
    )


@router.get("/{record_id}", response_model=AttendanceOut)
def get_attendance(
    record_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AttendanceOut:
    return AttendanceOut.model_validate(service.get_attendance(db, current, record_id))


@router.patch("/{record_id}", response_model=AttendanceOut)
def update_attendance(
    record_id: uuid.UUID,
    body: AttendanceUpdate,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> AttendanceOut:
    return AttendanceOut.model_validate(
        service.update_attendance(db, admin, record_id, body)
    )


@router.delete("/{record_id}", status_code=204)
def delete_attendance(
    record_id: uuid.UUID,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> Response:
    service.delete_attendance(db, admin, record_id)
    return Response(status_code=204)


@employee_router.get("/{employee_id}/attendance", response_model=AttendancePage)
def list_employee_attendance(
    employee_id: uuid.UUID,
    status: AttendanceStatus | None = Query(default=None),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AttendancePage:
    rows, total = service.list_employee_attendance(
        db,
        current,
        employee_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return AttendancePage(
        items=[AttendanceOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
