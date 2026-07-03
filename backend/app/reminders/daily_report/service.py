"""DailyReportReminderService — produces missing-report data per PM.

Responsibility (only): decide *who owes which reports* and return structured
data. It performs no SMTP, no HTML rendering, and no email decisions.

Business rules (reused from the existing report-compliance module so this stays
consistent with what employees already see):

  * A day "requires a report" for an employee only if they have a *worked*
    attendance record that day (present / half_day). This automatically excludes
    approved leave, holidays, week-offs, comp-off and absences, because those are
    not "worked" attendance statuses.
  * A report "satisfies" a day only once it is **submitted** (drafts do not).
  * The lookback is the previous N working days (Mon-Fri), strictly before today,
    default 7. Holidays that happen to fall on a weekday are still excluded via
    the attendance rule above.

Only employees currently assigned to a PM (``employees.reporting_pm_id``) are
considered, and only active PMs / active employees.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.attendance.models import AttendanceRecord
from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.report_compliance.service import WORKED_STATUSES
from app.modules.users.models import User, UserRole
from app.modules.work_reports.models import DailyWorkReport, WorkReportStatus

DEFAULT_LOOKBACK_WORKING_DAYS = 7


@dataclass(frozen=True)
class MissingEmployee:
    employee_id: uuid.UUID
    name: str


@dataclass(frozen=True)
class MissingReportDay:
    """One date and the employees who did not submit for it."""

    report_date: date
    employees: list[MissingEmployee]


@dataclass(frozen=True)
class PMReminder:
    """Everything the template/dispatcher needs for a single PM's email."""

    pm_id: uuid.UUID
    pm_name: str
    pm_email: str
    # Number of active employees assigned to this PM that were examined.
    employees_checked: int = 0
    # Most-recent date first (matches the "03 Jul / 02 Jul / 01 Jul" layout).
    days: list[MissingReportDay] = field(default_factory=list)

    @property
    def total_missing(self) -> int:
        return sum(len(d.employees) for d in self.days)


class DailyReportReminderService:
    """Collects per-PM missing-report reminders. Stateless; inject the session."""

    def __init__(self, lookback_working_days: int = DEFAULT_LOOKBACK_WORKING_DAYS) -> None:
        self.lookback_working_days = lookback_working_days

    def working_day_window(self, today: date) -> list[date]:
        """The previous ``lookback`` working days (Mon-Fri), strictly before today.

        Returned most-recent first. This is only an *upper bound* on how far back
        we nag; the attendance rule decides which of these actually owed a report.
        """
        days: list[date] = []
        cursor = today - timedelta(days=1)
        while len(days) < self.lookback_working_days:
            if cursor.weekday() < 5:  # Mon..Fri
                days.append(cursor)
            cursor -= timedelta(days=1)
        return days

    def collect(self, db: Session, *, today: date | None = None) -> list[PMReminder]:
        """Return one PMReminder per PM that has at least one missing report."""
        today = today or date.today()
        window = self.working_day_window(today)
        if not window:
            return []
        window_start, window_end = window[-1], window[0]
        window_set = set(window)

        pms = self._active_pms(db)
        if not pms:
            return []

        employees_by_pm = self._employees_by_pm(db, [pm.id for pm in pms])
        all_employee_ids = [e.id for emps in employees_by_pm.values() for e in emps]
        if not all_employee_ids:
            return []

        worked = self._worked_dates(db, all_employee_ids, window_start, window_end)
        submitted = self._submitted_dates(db, all_employee_ids, window_start, window_end)
        pm_names = self._pm_display_names(db, pms)

        reminders: list[PMReminder] = []
        for pm in pms:
            pm_employees = employees_by_pm.get(pm.id, [])
            days = self._missing_days_for_pm(
                pm_employees, worked, submitted, window_set
            )
            if not days:
                continue
            reminders.append(
                PMReminder(
                    pm_id=pm.id,
                    pm_name=pm_names[pm.id],
                    pm_email=pm.email,
                    employees_checked=len(pm_employees),
                    days=days,
                )
            )
        return reminders

    # -- query helpers -------------------------------------------------------

    def _active_pms(self, db: Session) -> list[User]:
        return list(
            db.execute(
                select(User).where(
                    User.role == UserRole.project_manager,
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                )
            ).scalars()
        )

    def _employees_by_pm(
        self, db: Session, pm_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[Employee]]:
        rows = db.execute(
            select(Employee).where(
                Employee.reporting_pm_id.in_(pm_ids),
                Employee.status == EmployeeStatus.active,
                Employee.deleted_at.is_(None),
            )
        ).scalars()
        grouped: dict[uuid.UUID, list[Employee]] = {}
        for emp in rows:
            grouped.setdefault(emp.reporting_pm_id, []).append(emp)
        return grouped

    def _worked_dates(
        self,
        db: Session,
        employee_ids: list[uuid.UUID],
        date_from: date,
        date_to: date,
    ) -> dict[uuid.UUID, set[date]]:
        rows = db.execute(
            select(AttendanceRecord.employee_id, AttendanceRecord.attendance_date).where(
                AttendanceRecord.employee_id.in_(employee_ids),
                AttendanceRecord.status.in_(WORKED_STATUSES),
                AttendanceRecord.attendance_date >= date_from,
                AttendanceRecord.attendance_date <= date_to,
            )
        ).all()
        result: dict[uuid.UUID, set[date]] = {}
        for emp_id, d in rows:
            result.setdefault(emp_id, set()).add(d)
        return result

    def _submitted_dates(
        self,
        db: Session,
        employee_ids: list[uuid.UUID],
        date_from: date,
        date_to: date,
    ) -> dict[uuid.UUID, set[date]]:
        rows = db.execute(
            select(DailyWorkReport.employee_id, DailyWorkReport.report_date).where(
                DailyWorkReport.employee_id.in_(employee_ids),
                DailyWorkReport.status == WorkReportStatus.submitted,
                DailyWorkReport.report_date >= date_from,
                DailyWorkReport.report_date <= date_to,
            )
        ).all()
        result: dict[uuid.UUID, set[date]] = {}
        for emp_id, d in rows:
            result.setdefault(emp_id, set()).add(d)
        return result

    def _pm_display_names(
        self, db: Session, pms: list[User]
    ) -> dict[uuid.UUID, str]:
        """PM first name via their Employee profile, falling back to the email."""
        pm_ids = [pm.id for pm in pms]
        profiles = db.execute(
            select(Employee).where(
                Employee.user_id.in_(pm_ids),
                Employee.deleted_at.is_(None),
            )
        ).scalars()
        first_name_by_user: dict[uuid.UUID, str] = {}
        for emp in profiles:
            if emp.user_id is not None:
                first_name_by_user.setdefault(emp.user_id, emp.first_name)
        names: dict[uuid.UUID, str] = {}
        for pm in pms:
            names[pm.id] = first_name_by_user.get(pm.id) or pm.email.split("@")[0]
        return names

    # -- grouping ------------------------------------------------------------

    def _missing_days_for_pm(
        self,
        employees: list[Employee],
        worked: dict[uuid.UUID, set[date]],
        submitted: dict[uuid.UUID, set[date]],
        window: set[date],
    ) -> list[MissingReportDay]:
        by_date: dict[date, list[MissingEmployee]] = {}
        for emp in employees:
            missing = (worked.get(emp.id, set()) & window) - submitted.get(emp.id, set())
            for d in missing:
                by_date.setdefault(d, []).append(
                    MissingEmployee(employee_id=emp.id, name=emp.full_name)
                )
        days: list[MissingReportDay] = []
        for d in sorted(by_date, reverse=True):  # most recent first
            employees_for_day = sorted(by_date[d], key=lambda e: e.name.lower())
            days.append(MissingReportDay(report_date=d, employees=employees_for_day))
        return days
