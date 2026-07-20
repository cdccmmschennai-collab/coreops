"""Daily Report Compliance schemas.

Read-only view over attendance vs. submitted work reports — no new tables.
Drives the employee 5:15 reminder, login banner, and logout guard.
"""
from datetime import date

from pydantic import BaseModel


class EmployeeComplianceOut(BaseModel):
    """The acting employee's own report-compliance snapshot for today plus
    any unfiled previous working days (within the editable submission window)."""
    has_attendance_today: bool
    has_report_today: bool
    pending_count: int
    pending_dates: list[date]
    # Split-day (migration 0060), all additive + WARN-ONLY — the date-level
    # report-existence rule above is unchanged. reported = the summed working
    # fractions of today's submitted report; attendance-required = 1.0 for a
    # 'present' attendance record, 0.5 for 'half_day', None when unknown.
    # Historical/current attendance never records WHICH half was worked, so a
    # mismatch only flags the report as possibly incomplete — it never blocks.
    reported_work_fraction_today: float | None = None
    attendance_work_fraction_today: float | None = None
    fraction_mismatch_today: bool = False
