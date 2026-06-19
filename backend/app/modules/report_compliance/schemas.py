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
