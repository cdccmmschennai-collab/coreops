"""Daily Report Compliance service.

Compares *attendance* (who actually worked) against *submitted work reports*
(who logged what they did) to surface an employee's own report gaps. There is no
new state: every value is derived live from attendance_records +
daily_work_reports.

Definitions used throughout:
  - a day "requires a report" for an employee if they worked it. Two things can
    establish that, and either is enough:
      * an attendance record with a *worked* status (present / half_day), i.e.
        a human ruled on the day; or
      * biometric punches the device settled as `present` - a full punch pair
        against the contracted shift, which is the same verdict the employee's
        own attendance calendar paints Present.
    absent / leave / holiday / weekend never require a report.

    The biometric half matters because most Present days are never typed in by
    anyone: the day is Present on screen purely because the person badged in and
    out. Reading only attendance_records meant those employees were invisible to
    compliance - no logout prompt, no banner, no pending day - which is exactly
    backwards, since they are the ones who definitely came to work.
  - a report "exists" for (employee, date) only once it is **submitted** — a
    draft does not satisfy compliance.
  - "previous working day" lookback is current + previous month. It stays a
    SUBSET of the report submission window (`work_reports.REPORTING_WINDOW_MONTHS`,
    6 months) on purpose: everything the banner nags about is fileable, but
    widening the filing window to let old reports be migrated in must not turn
    months of historical gaps into a standing pile of pending days.
"""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.biometric.service import settled_present_days
from app.modules.employees.service import _current_employee
from app.modules.users.models import User
from app.modules.work_reports.models import (
    NO_ACTIVITY_DAY_STATUSES,
    DailyWorkReport,
    DayStatus,
    WorkReportPeriod,
    WorkReportStatus,
)

# Attendance statuses that imply the employee worked and therefore owes a report.
WORKED_STATUSES = (AttendanceStatus.present, AttendanceStatus.half_day)


def _today() -> date:
    return date.today()


def _first_of_previous_month(today: date) -> date:
    first_of_this = today.replace(day=1)
    if first_of_this.month == 1:
        return first_of_this.replace(year=first_of_this.year - 1, month=12)
    return first_of_this.replace(month=first_of_this.month - 1)


def _attendance_statuses(
    db: Session, employee_id: uuid.UUID, *, date_from: date, date_to: date
) -> dict[date, AttendanceStatus]:
    """Every day in the window a human has ruled on, and how. One query.

    The whole map rather than just the worked days, because "nobody has ruled on
    this day" and "somebody ruled it leave" are different answers and only the
    first one may fall through to the biometric evidence.
    """
    rows = db.execute(
        select(AttendanceRecord.attendance_date, AttendanceRecord.status).where(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.attendance_date >= date_from,
            AttendanceRecord.attendance_date <= date_to,
        )
    ).all()
    return {day: status for day, status in rows}


def _biometric_present_dates(
    db: Session, employee_id: uuid.UUID, *, date_from: date, date_to: date
) -> set[date]:
    """Days in the window the DEVICE settled as a full day's attendance.

    Delegates to `biometric.settled_present_days`, the same helper the leave
    guard uses and the same boundary + classification rules the employee's
    calendar renders. Compliance owns no verdict of its own: a day counted here
    is a day the employee is looking at marked Present.

    Only `present` counts. `incomplete` (one punch) and `needs_review` mean the
    evidence did not settle the day, and demanding a work report on the strength
    of a single unpaired swipe would be a guess about whether they stayed.
    """
    return set(
        settled_present_days(
            db, employee_id=employee_id, date_from=date_from, date_to=date_to
        )
    )


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


def _reported_work_fraction(
    db: Session, employee_id: uuid.UUID, day: date
) -> float | None:
    """Summed working-period fractions of the employee's SUBMITTED report for
    `day` (split-day, migration 0060). Working = the period's status is a
    working one. A report without period rows (pre-period data) falls back to
    the header: leave-type day statuses 0.0, half_day 0.5, else 1.0. None when
    no submitted report exists."""
    report = db.execute(
        select(DailyWorkReport).where(
            DailyWorkReport.employee_id == employee_id,
            DailyWorkReport.report_date == day,
            DailyWorkReport.status == WorkReportStatus.submitted,
        )
    ).scalar_one_or_none()
    if report is None:
        return None
    periods = db.execute(
        select(WorkReportPeriod).where(WorkReportPeriod.report_id == report.id)
    ).scalars().all()
    if not periods:
        if report.day_status in NO_ACTIVITY_DAY_STATUSES:
            return 0.0
        return 0.5 if report.day_status == DayStatus.half_day else 1.0
    total = 0.0
    for p in periods:
        working = (
            p.period_status is not None
            and p.period_status not in NO_ACTIVITY_DAY_STATUSES
        )
        if working:
            total += float(p.work_fraction)
    return total


def _attendance_work_fraction(
    status: AttendanceStatus | None, *, biometric_present: bool
) -> float | None:
    """Work fraction the day implies: present 1.0, half_day 0.5, else None.
    Attendance does not record WHICH half was worked — callers may only compare
    magnitudes, never halves.

    Pure, and reading the status the caller already has rather than re-querying
    for a row it just loaded.

    A human's ruling is final either way: an explicit leave / absent / holiday
    returns None even when the device saw punches, because that ruling is the
    answer to "was this a working day" and observation does not overrule it.
    Only a day nobody has ruled on falls through to the device, where a settled
    `present` is a whole day - the device cannot express a half day, so this
    never returns 0.5 on biometric grounds.
    """
    if status == AttendanceStatus.present:
        return 1.0
    if status == AttendanceStatus.half_day:
        return 0.5
    if status is not None:
        return None
    return 1.0 if biometric_present else None


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
            "reported_work_fraction_today": None,
            "attendance_work_fraction_today": None,
            "fraction_mismatch_today": False,
        }

    window_start = _first_of_previous_month(today)
    statuses = _attendance_statuses(db, me.id, date_from=window_start, date_to=today)
    biometric = _biometric_present_dates(
        db, me.id, date_from=window_start, date_to=today
    )
    # A day is worked if a human said so, OR if nobody said anything and the
    # device settled it as Present. The `not in statuses` half is what keeps a
    # ruling authoritative: a day marked leave stays leave even with punches on
    # it, so an approved absence never starts demanding a work report.
    worked = {d for d, s in statuses.items() if s in WORKED_STATUSES} | {
        d for d in biometric if d not in statuses
    }
    submitted = _submitted_report_dates(db, me.id, date_from=window_start, date_to=today)

    # Previous working days (strictly before today) with attendance but no
    # submitted report — these are the "pending" reports the banner counts.
    pending = sorted(d for d in worked if d < today and d not in submitted)

    # Split-day awareness (warn-only): one submitted header still satisfies the
    # date-level requirement above, but a report whose working fraction doesn't
    # match what attendance implies is flagged as possibly incomplete.
    reported_fraction = _reported_work_fraction(db, me.id, today)
    attendance_fraction = _attendance_work_fraction(
        statuses.get(today), biometric_present=today in biometric
    )
    mismatch = (
        reported_fraction is not None
        and attendance_fraction is not None
        and reported_fraction != attendance_fraction
    )
    return {
        "has_attendance_today": today in worked,
        "has_report_today": today in submitted,
        "pending_count": len(pending),
        "pending_dates": pending,
        "reported_work_fraction_today": reported_fraction,
        "attendance_work_fraction_today": attendance_fraction,
        "fraction_mismatch_today": mismatch,
    }
