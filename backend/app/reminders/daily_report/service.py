"""DailyReportReminderService — produces missing-report data per PM.

Responsibility (only): decide *who owes the report* and return structured data.
It performs no SMTP, no HTML rendering, and no email decisions.

Business rules:

  * Exactly ONE date is ever checked: the **immediately previous working day**
    relative to ``today``. Weekends and company-calendar non-working days are
    skipped (see ``app.modules.calendar.working_days``), so a Monday run targets
    the previous Friday, and a run the day after a holiday targets the last day
    the office was actually open. Older gaps are never chased: an employee who
    missed two days ago but filed for the target day does not appear.
  * That day "requires a report" for an employee if it is on or after their
    ``date_of_joining``. This does *not* depend on attendance being recorded.
  * A report "satisfies" the day once it is **submitted** or **granted** (a
    report reopened for editing is still a recorded report; drafts never satisfy
    the day). Task/benchmark completion state is irrelevant — only that a report
    exists.

Only employees currently assigned to a PM (``employees.reporting_pm_id``) are
considered, and only active PMs / active employees.

Employees whose linked user account has the global ``project_manager`` role are
never treated as report submitters: they are excluded here, in the data layer, so
that every downstream count (``employees_checked``, ``total_missing``, the email
table, and the CSV) agrees. PMs still *receive* reminders for the employees who
report to them.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.calendar.working_days import (
    DEFAULT_MAX_LOOKBACK_DAYS,
    previous_working_day,
)
from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.leave.models import LeaveRequest, LeaveStatus
from app.modules.users.models import User, UserRole
from app.modules.work_reports.models import DailyWorkReport, WorkReportStatus

# Leave states that still count as an active absence on the target date, so a
# missing report must not be raised for them. `cancellation_requested` stays
# here because the leave model treats the absence as still in force until the
# cancellation is actually decided.
_ACTIVE_LEAVE_STATUSES = (LeaveStatus.approved, LeaveStatus.cancellation_requested)

logger = logging.getLogger("coreops.reminders.daily_report")


@dataclass(frozen=True)
class MissingEmployee:
    employee_id: uuid.UUID
    name: str
    # Human-facing staff code (e.g. "EMP225"). Shown in the reminder email.
    code: str = ""


@dataclass(frozen=True)
class PMReminder:
    """Everything the template/dispatcher needs for a single PM's email.

    ``report_date`` is the one previous working day the run checked; every
    employee in ``employees`` is missing that single date, so an employee can
    never carry more than one missing-date value.
    """

    pm_id: uuid.UUID
    pm_name: str
    pm_email: str
    report_date: date
    # Number of active, report-owing employees assigned to this PM that were examined.
    employees_checked: int = 0
    # Sorted by employee name.
    employees: list[MissingEmployee] = field(default_factory=list)

    @property
    def total_missing(self) -> int:
        return len(self.employees)


class DailyReportReminderService:
    """Collects per-PM missing-report reminders. Stateless; inject the session."""

    def __init__(self, max_lookback_days: int = DEFAULT_MAX_LOOKBACK_DAYS) -> None:
        # Only a safety bound on the backwards walk for the previous working day;
        # it is not a lookback window. Exactly one date is ever reported on.
        self.max_lookback_days = max_lookback_days

    def target_date(self, db: Session, today: date) -> date | None:
        """The single date this run chases: the previous working day.

        ``None`` when the calendar declares no working day within the safety
        bound, in which case the run reports nothing.
        """
        return previous_working_day(
            db, today, max_lookback_days=self.max_lookback_days
        )

    def collect(self, db: Session, *, today: date | None = None) -> list[PMReminder]:
        """Return one PMReminder per PM that has at least one missing report."""
        today = today or date.today()
        target = self.target_date(db, today)
        if target is None:
            logger.warning(
                "reminder.no_working_day today=%s lookback_days=%d",
                today,
                self.max_lookback_days,
            )
            return []

        pms = self._active_pms(db)
        if not pms:
            return []

        employees_by_pm = self._employees_by_pm(db, [pm.id for pm in pms])
        all_employee_ids = [e.id for emps in employees_by_pm.values() for e in emps]
        if not all_employee_ids:
            return []

        reported = self._employees_with_report(db, all_employee_ids, target)
        on_leave = self._employees_on_leave(db, all_employee_ids, target)
        pm_names = self._pm_display_names(db, pms)

        reminders: list[PMReminder] = []
        for pm in pms:
            pm_employees = employees_by_pm.get(pm.id, [])
            missing = self._missing_employees(pm_employees, reported, on_leave, target)
            if not missing:
                continue
            reminders.append(
                PMReminder(
                    pm_id=pm.id,
                    pm_name=pm_names[pm.id],
                    pm_email=pm.email,
                    report_date=target,
                    employees_checked=len(pm_employees),
                    employees=missing,
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

    def _employees_with_report(
        self, db: Session, employee_ids: list[uuid.UUID], target: date
    ) -> set[uuid.UUID]:
        """Employees who have a recorded report for the target date.

        A report counts as recorded once it is ``submitted`` or ``granted`` (a
        report the Project Head reopened for editing is still a recorded report).
        Drafts do not count. Task/benchmark completion is never consulted — only
        that a report row exists for the date.
        """
        rows = db.execute(
            select(DailyWorkReport.employee_id).where(
                DailyWorkReport.employee_id.in_(employee_ids),
                DailyWorkReport.status.in_(
                    [WorkReportStatus.submitted, WorkReportStatus.granted]
                ),
                DailyWorkReport.report_date == target,
            )
        ).scalars()
        return set(rows)

    def _employees_on_leave(
        self, db: Session, employee_ids: list[uuid.UUID], target: date
    ) -> set[uuid.UUID]:
        """Employees whose leave is active over the target date.

        Active here means it would still suppress a missing-report: ``approved``
        or ``cancellation_requested`` (the absence stands until the cancellation
        is actually decided). ``pending``, ``rejected`` and ``cancelled`` never
        suppress.
        """
        rows = db.execute(
            select(LeaveRequest.employee_id).where(
                LeaveRequest.employee_id.in_(employee_ids),
                LeaveRequest.status.in_(_ACTIVE_LEAVE_STATUSES),
                LeaveRequest.start_date <= target,
                LeaveRequest.end_date >= target,
            )
        ).scalars()
        return set(rows)

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
    def _owes_report(emp: Employee, target: date) -> bool:
        """Whether the employee owed a report on the target day.

        A day strictly before the employee's joining date is not owed. A missing
        joining date is treated as "no clamp".
        """
        return emp.date_of_joining is None or target >= emp.date_of_joining

    def _missing_employees(
        self,
        employees: list[Employee],
        reported: set[uuid.UUID],
        on_leave: set[uuid.UUID],
        target: date,
    ) -> list[MissingEmployee]:
        missing = [
            MissingEmployee(
                employee_id=emp.id, name=emp.full_name, code=emp.employee_code
            )
            for emp in employees
            if self._owes_report(emp, target)
            and emp.id not in reported
            and emp.id not in on_leave
        ]
        missing.sort(key=lambda e: e.name.lower())
        return missing
