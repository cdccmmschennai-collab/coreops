"""Daily Report Compliance service.

Compares *attendance* (who actually worked) against *submitted work reports*
(who logged what they did) to surface an employee's own report gaps. There is no
new state: every value is derived live from attendance_records +
daily_work_reports.

Definitions used throughout:
  - a day "requires a report" for an employee if they have an attendance record
    that day with a *worked* status (present / half_day). absent / leave /
    holiday / weekend never require a report.
  - a report "exists" for (employee, date) only once it is **submitted** — a
    draft does not satisfy compliance.
  - "previous working day" lookback is bounded by the report submission window
    (current + previous month) so every pending day is actually fileable.
"""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.employees.service import _current_employee
from app.modules.users.models import User
from app.modules.work_reports.models import DailyWorkReport, WorkReportStatus

# Attendance statuses that imply the employee worked and therefore owes a report.
WORKED_STATUSES = (AttendanceStatus.present, AttendanceStatus.half_day)


def _today() -> date:
    return date.today()


def _first_of_previous_month(today: date) -> date:
    first_of_this = today.replace(day=1)
    if first_of_this.month == 1:
        return first_of_this.replace(year=first_of_this.year - 1, month=12)
    return first_of_this.replace(month=first_of_this.month - 1)


def _worked_attendance_dates(
    db: Session, employee_id: uuid.UUID, *, date_from: date, date_to: date
) -> set[date]:
    rows = db.execute(
        select(AttendanceRecord.attendance_date).where(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.status.in_(WORKED_STATUSES),
            AttendanceRecord.attendance_date >= date_from,
            AttendanceRecord.attendance_date <= date_to,
        )
    ).scalars().all()
    return set(rows)


def _submitted_report_dates(
    db: Session, employee_id: uuid.UUID, *, date_from: date, date_to: date
) -> set[date]:
    rows = db.execute(
        select(DailyWorkReport.report_date).where(
            DailyWorkReport.employee_id == employee_id,
            DailyWorkReport.status == WorkReportStatus.submitted,
            DailyWorkReport.report_date >= date_from,
            DailyWorkReport.report_date <= date_to,
        )
    ).scalars().all()
    return set(rows)


def employee_compliance(db: Session, actor: User) -> dict:
    """Own compliance snapshot. Users without an employee profile (or who never
    have attendance) simply see an all-clear result."""
    me = _current_employee(db, actor)
    today = _today()
    if me is None:
        return {
            "has_attendance_today": False,
            "has_report_today": False,
            "pending_count": 0,
            "pending_dates": [],
        }

    window_start = _first_of_previous_month(today)
    worked = _worked_attendance_dates(db, me.id, date_from=window_start, date_to=today)
    submitted = _submitted_report_dates(db, me.id, date_from=window_start, date_to=today)

    # Previous working days (strictly before today) with attendance but no
    # submitted report — these are the "pending" reports the banner counts.
    pending = sorted(d for d in worked if d < today and d not in submitted)
    return {
        "has_attendance_today": today in worked,
        "has_report_today": today in submitted,
        "pending_count": len(pending),
        "pending_dates": pending,
    }
