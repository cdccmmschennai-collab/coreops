"""Attendance pydantic schemas (mirrors employees/projects).

total_minutes and overtime_minutes are derived server-side (read-only output);
they are not accepted on create/update.
"""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.modules.attendance.models import AttendanceStatus


class AttendanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    attendance_date: date
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    total_minutes: int
    overtime_minutes: int
    status: AttendanceStatus
    created_at: datetime


class AttendanceCreate(BaseModel):
    employee_id: uuid.UUID
    attendance_date: date
    status: AttendanceStatus
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None


class AttendanceUpdate(BaseModel):
    status: AttendanceStatus | None = None
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None


class AttendancePage(BaseModel):
    items: list[AttendanceOut]
    total: int
    limit: int
    offset: int


# ---------- bulk / sheet ----------------------------------------------------
class AttendanceSheetRow(BaseModel):
    """One employee's line on the day's attendance sheet.

    record_id is None when no attendance is saved for this employee/date yet
    (the row defaults to ``present``). total/overtime minutes are derived.
    """

    employee_id: uuid.UUID
    employee_code: str
    employee_name: str
    status: AttendanceStatus
    record_id: uuid.UUID | None = None
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    total_minutes: int = 0
    overtime_minutes: int = 0


class AttendanceSheet(BaseModel):
    attendance_date: date
    # True when attendance was already recorded for the date (edit vs new).
    exists: bool
    rows: list[AttendanceSheetRow]


class AttendanceBulkRecord(BaseModel):
    employee_id: uuid.UUID
    status: AttendanceStatus
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None


class AttendanceBulkSave(BaseModel):
    date: date
    records: list[AttendanceBulkRecord]
