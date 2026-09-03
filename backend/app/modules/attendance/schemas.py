"""Attendance pydantic schemas (mirrors employees/projects).

total_minutes and overtime_minutes are derived server-side (read-only output);
they are not accepted on create/update.
"""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.attendance.models import AttendanceStatus
from app.shared.leave_units import validate_half_step

# A reviewer's note is a sentence, not an essay. Bounded so the audit `details`
# JSON stays a predictable size.
MAX_NOTE_LEN = 500


def _validate_leave_fraction(value: float | None) -> float | None:
    """A day is 0, half or all leave - never 0.4 of it.

    Mirrors the `attendance_leave_fraction_half_steps` check constraint so the
    API refuses the value with a readable message instead of letting the
    database reject it as a 500.
    """
    if value is None:
        return None
    return validate_half_step(value, "Leave for a day", minimum=0, maximum=1)


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
    # How much of the day was funded leave (migration 0083). Null means the day
    # never stated one and is priced by status alone - see
    # `leave_balances.ledger.leave_days_for`.
    leave_day_fraction: float | None = None
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
    # How much of this day the leave pool pays for: 0.5 marks a HALF-DAY LEAVE,
    # which is the case `status` alone cannot express. Omitted leaves the day
    # priced by status, exactly as before migration 0083.
    leave_day_fraction: float | None = None

    @field_validator("leave_day_fraction")
    @classmethod
    def _check_fraction(cls, value: float | None) -> float | None:
        return _validate_leave_fraction(value)


class AttendanceUpdate(BaseModel):
    status: AttendanceStatus | None = None
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    note: str | None = Field(default=None, max_length=MAX_NOTE_LEN)
    leave_day_fraction: float | None = None

    @field_validator("leave_day_fraction")
    @classmethod
    def _check_fraction(cls, value: float | None) -> float | None:
        return _validate_leave_fraction(value)


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
