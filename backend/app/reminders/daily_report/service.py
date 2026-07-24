"""DailyReportReminderService — produces missing-report data per PM.

Responsibility (only): decide *who owes which reports* and return structured
data. It performs no SMTP, no HTML rendering, and no email decisions.

Business rules:

  * A day "requires a report" for an employee if it is a working day (Mon-Fri)
    in the lookback window, on or after the employee's ``date_of_joining``. This
    does *not* depend on attendance being recorded.
  * A report "satisfies" a day once it is **submitted** or **granted** (a report
    reopened for editing is still a recorded report; drafts never satisfy a day).
    Task/benchmark completion state is irrelevant — only that a report exists.
  * The lookback is the previous N working days (Mon-Fri), strictly before today,
    default 3.

Only employees currently assigned to a PM (``employees.reporting_pm_id``) are
considered, and only active PMs / active employees.

Employees whose linked user account has the global ``project_manager`` role are
never treated as report submitters: they are excluded here, in the data layer, so
that every downstream count (``employees_checked``, ``total_missing``, the email
table, and the CSV) agrees. PMs still *receive* reminders for the employees who
report to them.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.users.models import User, UserRole
from app.modules.work_reports.models import DailyWorkReport, WorkReportStatus

DEFAULT_LOOKBACK_WORKING_DAYS = 3


@dataclass(frozen=True)
class MissingEmployee:
    employee_id: uuid.UUID
    name: str
    # Human-facing staff code (e.g. "EMP225"). Shown in the reminder email.
    code: str = ""


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

        Returned most-recent first. This is the set of days a report is owed for;
        the per-employee joining-date clamp narrows it further.
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

        recorded = self._recorded_dates(db, all_employee_ids, window_start, window_end)
        pm_names = self._pm_display_names(db, pms)

        reminders: list[PMReminder] = []
        for pm in pms:
            pm_employees = employees_by_pm.get(pm.id, [])
            days = self._missing_days_for_pm(
                pm_employees, recorded, window_set
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
        # Users with the global project_manager role do not submit daily reports,
        # so their employee records are dropped before anything is counted.
        pm_user_ids = select(User.id).where(User.role == UserRole.project_manager)
        rows = db.execute(
            select(Employee).where(
                Employee.reporting_pm_id.in_(pm_ids),
                Employee.status == EmployeeStatus.active,
                Employee.deleted_at.is_(None),
                # An employee with no login cannot be a PM; ``NOT IN`` alone would
                # discard those rows because NULL NOT IN (...) is NULL.
                or_(
                    Employee.user_id.is_(None),
                    Employee.user_id.notin_(pm_user_ids),
                ),
            )
        ).scalars()
        grouped: dict[uuid.UUID, list[Employee]] = {}
        for emp in rows:
            grouped.setdefault(emp.reporting_pm_id, []).append(emp)
        return grouped

    def _recorded_dates(
        self,
        db: Session,
        employee_ids: list[uuid.UUID],
        date_from: date,
        date_to: date,
    ) -> dict[uuid.UUID, set[date]]:
        """Dates each employee has a recorded report for, in the window.

        A report counts as recorded once it is ``submitted`` or ``granted`` (a
        report the Project Head reopened for editing is still a recorded report).
        Drafts do not count. Task/benchmark completion is never consulted — only
        that a report row exists for the date.
        """
        rows = db.execute(
            select(DailyWorkReport.employee_id, DailyWorkReport.report_date).where(
                DailyWorkReport.employee_id.in_(employee_ids),
                DailyWorkReport.status.in_(
                    [WorkReportStatus.submitted, WorkReportStatus.granted]
                ),
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

    @staticmethod
    def _owed_days(emp: Employee, window: set[date]) -> set[date]:
        """Working days in the window the employee owes a report for.

        Every working day counts (attendance is no longer required); days strictly
        before the employee's joining date are excluded. A missing joining date is
        treated as "no clamp" (the whole window is owed).
        """
        joining = emp.date_of_joining
        if joining is None:
            return set(window)
        return {d for d in window if d >= joining}

    def _missing_days_for_pm(
        self,
        employees: list[Employee],
        recorded: dict[uuid.UUID, set[date]],
        window: set[date],
    ) -> list[MissingReportDay]:
        by_date: dict[date, list[MissingEmployee]] = {}
        for emp in employees:
            missing = self._owed_days(emp, window) - recorded.get(emp.id, set())
            for d in missing:
                by_date.setdefault(d, []).append(
                    MissingEmployee(
                        employee_id=emp.id,
                        name=emp.full_name,
                        code=emp.employee_code,
                    )
                )
        days: list[MissingReportDay] = []
        for d in sorted(by_date, reverse=True):  # most recent first
            employees_for_day = sorted(by_date[d], key=lambda e: e.name.lower())
            days.append(MissingReportDay(report_date=d, employees=employees_for_day))
        return days
