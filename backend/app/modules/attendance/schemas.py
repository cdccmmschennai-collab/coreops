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
