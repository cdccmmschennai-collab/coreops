"""Attendance pydantic schemas (mirrors employees/projects).

total_minutes and overtime_minutes are derived server-side (read-only output);
they are not accepted on create/update.
"""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.attendance.models import AttendanceStatus

# A reviewer's note is a sentence, not an essay. Bounded so the audit `details`
# JSON stays a predictable size.
MAX_NOTE_LEN = 500


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
    # Why a human set this day this way (migration 0067). Null is normal.
    note: str | None = None
    created_at: datetime


class AttendanceCreate(BaseModel):
    employee_id: uuid.UUID
    attendance_date: date
    status: AttendanceStatus
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    # Why the PM set this day the way they did. NOT a column on
    # `attendance_records` - it is recorded in the audit trail alongside the
    # change, which is where the reasoning for a human decision belongs. Storing
    # it on the row as well would need a migration; see the Phase 8 report.
    note: str | None = Field(default=None, max_length=MAX_NOTE_LEN)


class AttendanceUpdate(BaseModel):
    status: AttendanceStatus | None = None
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    note: str | None = Field(default=None, max_length=MAX_NOTE_LEN)


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
