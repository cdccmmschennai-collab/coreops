"""Attendance pydantic schemas (mirrors employees/projects).

total_minutes and overtime_minutes are derived server-side (read-only output);
they are not accepted on create/update.
"""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.attendance.models import AttendanceStatus
from app.modules.permissions.models import PermissionPeriod
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
    # The PM's manual permission for this day - one of the request workflow's own
    # four options, or null for "No Permission". OMITTED leaves the day's
    # permission exactly as it is; only a field that was actually sent is acted
    # on (see `permissions.service.apply_manual_permission`). Never a status:
    # the day keeps `status` whatever this says.
    permission_period: PermissionPeriod | None = None

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
    # Same contract as `AttendanceCreate.permission_period`.
    permission_period: PermissionPeriod | None = None

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
    # One reason for the whole batch. Required when `date` is in the past.
    note: str | None = Field(default=None, max_length=MAX_NOTE_LEN)


# ---------- bulk apply (Phase 4) --------------------------------------------
# Bounds on one bulk action. A month of dates for a team, or a whole team on
# one day, fits comfortably; anything larger is a mistake or a script.
MAX_BULK_EMPLOYEES = 200
MAX_BULK_DATES = 62
MAX_BULK_PAIRS = 500

BulkApplyOutcome = Literal["created", "updated", "unchanged", "protected", "rejected"]


class AttendanceBulkApply(BaseModel):
    """One status applied to every (employee, date) pair of employees x dates.

    One employee across many dates and many employees on one date are both
    this shape. STATUS ONLY: check-in/out and permission data are never written.
    `dry_run` defaults to True so a client that forgets it previews, not writes.
    """

    employee_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_BULK_EMPLOYEES)
    dates: list[date] = Field(min_length=1, max_length=MAX_BULK_DATES)
    status: AttendanceStatus
    # The action's one reason. Required for every PAST pair that would change.
    note: str | None = Field(default=None, max_length=MAX_NOTE_LEN)
    # Non-working days (weekly off, company holiday) are skipped unless set.
    include_non_working: bool = False
    dry_run: bool = True

    @model_validator(mode="after")
    def _check_size(self) -> "AttendanceBulkApply":
        if len(self.employee_ids) * len(self.dates) > MAX_BULK_PAIRS:
            raise ValueError(
                f"A bulk action can cover at most {MAX_BULK_PAIRS} employee-days."
            )
        return self


class AttendanceBulkWarning(BaseModel):
    code: str
    message: str


class AttendanceBulkApplyItem(BaseModel):
    """What happened (or, in a preview, would happen) to one employee-day."""

    employee_id: uuid.UUID
    employee_code: str | None = None
    employee_name: str | None = None
    attendance_date: date
    outcome: BulkApplyOutcome
    # Machine-readable why, for protected / rejected / unchanged outcomes.
    reason_code: str | None = None
    message: str | None = None
    record_id: uuid.UUID | None = None
    previous_status: AttendanceStatus | None = None
    # The day's status after the action (or in the preview, after applying).
    status: AttendanceStatus | None = None
    warnings: list[AttendanceBulkWarning] = []


class AttendanceBulkApplySummary(BaseModel):
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    protected: int = 0
    rejected: int = 0


class AttendanceBulkApplyResult(BaseModel):
    dry_run: bool
    # Set on an applied action; the same id is on every audit entry it wrote.
    bulk_action_id: uuid.UUID | None = None
    status: AttendanceStatus
    summary: AttendanceBulkApplySummary
    results: list[AttendanceBulkApplyItem]
