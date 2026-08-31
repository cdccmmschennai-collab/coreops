"""Automatic (system-generated) Daily Work Reports - Phase 3C: WEEKENDS ONLY.

WHAT THIS DOES
==============
For a date the company calendar says the office is closed, every active
report-submitting employee who has no report of their own for that date gets one
created for them:

    origin        = auto
    status        = submitted
    day_status    = week_off
    report_mode   = full_day
    total_minutes = 0

That is the whole behaviour. Nothing here approves, notifies, locks, emails, or
deletes anything.

SUBMITTED, NOT DRAFT - AND WHY NOT VIA submit_work_report()
===========================================================
A closed day has no reporting obligation left to discharge, so the report is
born already accounting for the day: a draft would leave the employee looking
like they still owe something for a Sunday.

The status is written DIRECTLY on the new row. `service.submit_work_report` is
deliberately NOT called, because everything it does besides setting the status is
wrong for a row nobody authored:

    _apply_benchmarks(...)      benchmark figures for a day with no work
    _assert_periods_submittable rules for periods this report will never have
    validate_report_activity_access  activity access for zero task rows
    report.updated_by = actor.id     there is no actor
    the `status in _EDITABLE` gate   a brand-new row is not being transitioned

`submitted_at` IS set, to the generation time. Not to claim a person submitted
it, but because `status == submitted AND submitted_at IS NULL` is a combination
no existing code path has ever produced - `submit_work_report` sets both and the
reopen path in `update_work_report` clears both - and future code is entitled to
assume the two move together.

SUBMITTED IS NOT LOCKED
=======================
Status and editability are separate questions here, and this module answers the
second one for AUTO rows via :func:`auto_report_author_editable`:

    AUTO + week_off / holiday / natural hazard -> the author may still edit
    AUTO + leave                               -> locked while the leave stands

Phase 3C only ever produces `week_off`, so the locked branch is unreachable
today; it is written as the default-deny half of the rule so that the phase which
starts generating leave reports cannot forget it.

The edit itself reuses the mechanism already in `update_work_report`: an author
editing a submitted AUTO report REOPENS it to draft exactly as a Project Head
editing their own submitted report does, and resubmits normally. That way
benchmarks recompute, no report is silently mutated while still marked
"submitted", and no new status/timestamp combination is invented.

THE CALENDAR IS THE SOURCE OF TRUTH
===================================
Whether a day is worked is decided by `calendar.working_days.is_working_day` and
by nothing else here. The weekend rule (Mon-Fri plus the 1st/3rd/5th Saturday) is
NOT restated in this module - restating it is exactly how two copies drift apart.
`working_days` stays a pure calculation: this module does the SQL and the writes,
it does not push either back into the calendar utility.

The consequence that matters most:

    Saturday, no override            -> non-working -> AUTO report created
    Saturday, `working_day` override -> working     -> NO AUTO report

A declared `working_day` beats the weekend rule inside `is_working_day`, so the
override needs no special case here; it simply never reaches the create branch.

WHY 'week_off' AND NOT 'company_holiday'
========================================
Phase 3C generates for CALENDAR-CLOSED days and labels them all `week_off`. It
does not yet distinguish a plain weekend from a declared holiday or a natural
hazard - those get their own day_status in a later phase. A declared holiday on a
weekday therefore also produces a `week_off` report today; that is a known,
deliberate Phase 3C simplification, not an accident, and it is the one thing a
later phase must refine rather than rebuild.

AN EMPLOYEE'S OWN REPORT ALWAYS WINS
====================================
If ANY report row already exists for (employee, date) the generator does nothing
at all to it. It does not overwrite, does not restamp `origin`, does not touch
`day_status`, does not delete. This holds whether the existing row was written by
the employee or by a previous run of this generator, and it is the rule that
makes the job safe to run at any hour, any number of times.

Existence is checked first because that gives a clean, countable outcome; the
`work_reports_emp_date_uq` unique constraint remains the FINAL protection, and
the IntegrityError path below treats a lost race as "already exists" rather than
as a failure.

IDEMPOTENCY
===========
Run 1 creates N reports. Run 2 and every run after it create none. There is no
"when did this last run" state anywhere - the answer is read off the reports
table itself, which is why a worker that was down for three days catches up
simply by running once, and why a run that died half way through resumes cleanly.

That is also why the scheduled job sweeps a WINDOW of recent dates rather than a
single one (see `generate_auto_reports`): re-covering a date that is already
covered costs one SELECT and writes nothing.

RECONCILIATION - PHASE 3D
=========================
The generator answers "what does the calendar say NOW"; it has no memory. So this
sequence leaves a row behind that no re-run can fix:

    Saturday 00:00  calendar says non-working  -> AUTO week_off report created
    Saturday 07:00  PM adds a `working_day` override for that Saturday
                    -> the office IS open, so the AUTO report is now STALE

Re-running the generator cannot repair it: the slot is taken, and "an existing
report always wins" (above) forbids touching it. Only a calendar CHANGE knows the
date flipped, so reconciliation hangs off that event -
:func:`reconcile_auto_reports_for_calendar_change`, called by
`calendar.service` from create / update / delete inside the same transaction as
the calendar write.

The stale row is findable because the two facts that identify it are both stored
and never mutated afterwards:

    daily_work_reports.origin     = 'auto'      (who created it)
    daily_work_reports.day_status = 'week_off'  (what it was created for)

so the query is exactly

    origin = auto AND day_status = week_off AND report_date IN (<changed dates>)

with no risk of touching an employee's own week_off report - that one carries
origin = 'employee'.

Nothing in this module may therefore convert an existing AUTO report into an
employee report, clear its day_status outside reconciliation, or "adopt" it on
edit. Doing so would erase the only evidence reconciliation has to work with.
There is a regression test pinning this (`test_auto_report_stays_identifiable_*`).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.modules.calendar.working_days import is_working_day, load_calendar_overrides
from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.users.models import User, UserRole
from app.modules.work_reports.models import (
    DAY_PART_FRACTIONS,
    DailyWorkReport,
    DayPart,
    DayStatus,
    ReportMode,
    ReportOrigin,
    WorkReportPeriod,
    WorkReportStatus,
    WorkReportTask,
)

logger = logging.getLogger("coreops.work_reports.auto_reports")

# The day_status every Phase 3C automatic report carries. Named here so the
# future reconciliation query has one constant to import rather than a literal
# copied into a second place.
AUTO_WEEKEND_DAY_STATUS = DayStatus.week_off

# The day statuses whose AUTOMATIC report is locked to its author. Only `leave`:
# an automatic leave report must not be edited while the leave stands. Every
# other automatic report - week_off now, holiday and natural hazard later - stays
# editable despite being submitted. Phase 3C generates no leave reports, so this
# set matches nothing yet; it is stated now so the rule is default-deny rather
# than an omission a later phase has to remember.
AUTO_LOCKED_DAY_STATUSES = frozenset({DayStatus.leave})

# How many days back the scheduled sweep re-checks, ending at `today`. Not a
# lookback "window" in the reminder sense: because the generator is idempotent,
# re-covering an already covered date writes nothing, so this is purely the
# self-healing margin for a worker that was down, ran late, or died mid-run.
DEFAULT_LOOKBACK_DAYS = 7


def auto_report_author_editable(report: DailyWorkReport) -> bool:
    """Whether this report's AUTHOR may edit it even though it is submitted.

    True only for an AUTOMATIC report whose day status is not in
    :data:`AUTO_LOCKED_DAY_STATUSES`. An employee-authored report always returns
    False here and is therefore governed entirely by the existing
    draft/rejected/granted rules - this predicate can only ever ADD permission to
    a row the generator created, never remove one from a row a person wrote.
    """
    return (
        report.origin == ReportOrigin.auto
        and report.day_status not in AUTO_LOCKED_DAY_STATUSES
    )


@dataclass(frozen=True)
class AutoReportOutcome:
    """What happened for one (employee, date) pair."""

    employee_id: uuid.UUID
    report_date: date
    # One of: "created", "working_day", "report_exists", "error".
    reason: str
    report_id: uuid.UUID | None = None
    error: str | None = None

    @property
    def created(self) -> bool:
        return self.reason == "created"


@dataclass
class AutoReportRunResult:
    dates: list[date] = field(default_factory=list)
    # DATES in the swept range the calendar reported as working - counted per
    # date, not per employee, because a working day is settled before any
    # employee is looked at.
    working_dates: int = 0
    # Employees examined, summed over the non-working dates only.
    employees_considered: int = 0
    created: int = 0
    skipped_existing: int = 0
    failed: int = 0
    outcomes: list[AutoReportOutcome] = field(default_factory=list)


def report_submitters(db: Session, target: date) -> list[Employee]:
    """The employees who could owe a report on `target`.

    Every filter is one the system already applies elsewhere - none of them is a
    new concept:

      status/soft-delete  `status == active` and `deleted_at IS NULL`, the same
                          pair `DailyReportReminderService._employees_by_pm` and
                          `reminders.leave_balance.eligible_employees` select by.
      PM logins           an employee whose login carries the global
                          `project_manager` role does not file daily reports, so
                          they are dropped here exactly as the reminder drops
                          them. The `user_id IS NULL` arm is required: an
                          employee with no login can never be a PM, and a bare
                          `NOT IN` would discard those rows because
                          `NULL NOT IN (...)` is NULL.
      joining date        a day before the employee joined was never owed, which
                          is the reminder's `_owes_report` rule expressed as SQL.
                          A missing joining date means no clamp.

    Deliberately NOT filtered by `reporting_pm_id`: the reminder needs a PM
    because it emails one, and this job emails nobody. An employee between PMs
    still has weekends, and the two populations can never disagree on a date
    anyway - the reminder only ever targets a WORKING day and this job only ever
    a non-working one.
    """
    pm_user_ids = select(User.id).where(User.role == UserRole.project_manager)
    return list(
        db.execute(
            select(Employee)
            .where(
                Employee.status == EmployeeStatus.active,
                Employee.deleted_at.is_(None),
                or_(
                    Employee.user_id.is_(None),
                    Employee.user_id.notin_(pm_user_ids),
                ),
                or_(
                    Employee.date_of_joining.is_(None),
                    Employee.date_of_joining <= target,
                ),
            )
            .order_by(Employee.employee_code)
        )
        .scalars()
        .all()
    )


def existing_report_employee_ids(
    db: Session, employee_ids: list[uuid.UUID], target: date
) -> set[uuid.UUID]:
    """Employees who already have ANY report row for `target`.

    Status is deliberately not consulted. The reminder asks "is the day
    accounted for" and so requires `submitted`/`granted`; this job asks "is the
    (employee, date) slot taken", and a draft takes it just as firmly - the
    unique constraint does not care what state the row is in.
    """
    if not employee_ids:
        return set()
    return set(
        db.execute(
            select(DailyWorkReport.employee_id).where(
                DailyWorkReport.employee_id.in_(employee_ids),
                DailyWorkReport.report_date == target,
            )
        ).scalars()
    )


def ensure_auto_report(
    db: Session,
    employee: Employee,
    report_date: date,
    *,
    non_working: set[date] | None = None,
    working_overrides: set[date] | None = None,
    commit: bool = True,
) -> AutoReportOutcome:
    """Create the automatic week-off report for one employee and one date, if
    the calendar says the office was closed and the slot is free.

    Idempotent and non-destructive: an existing report of ANY origin or status
    is left exactly as it is.

    `non_working` / `working_overrides` come from
    :func:`calendar.working_days.load_calendar_overrides`. Pass them when
    sweeping many employees over the same dates so the calendar is read once;
    omit them and this call loads the one date itself, so it stands alone.
    """
    if non_working is None or working_overrides is None:
        non_working, working_overrides = load_calendar_overrides(
            db, report_date, report_date
        )

    # The single business decision, delegated whole to the calendar. A
    # `working_day` override on a Saturday lands here as True and stops the run
    # for that date - that is the rule this phase exists to honour.
    if is_working_day(
        report_date, non_working=non_working, working_overrides=working_overrides
    ):
        return AutoReportOutcome(
            employee_id=employee.id, report_date=report_date, reason="working_day"
        )

    existing = db.execute(
        select(DailyWorkReport).where(
            DailyWorkReport.employee_id == employee.id,
            DailyWorkReport.report_date == report_date,
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Nothing is read off it, nothing is written to it. Whether the employee
        # typed it or a previous run generated it, it stands untouched.
        return AutoReportOutcome(
            employee_id=employee.id,
            report_date=report_date,
            reason="report_exists",
            report_id=existing.id,
        )

    report = DailyWorkReport(
        employee_id=employee.id,
        report_date=report_date,
        # Born submitted: a closed day has no reporting obligation left to
        # discharge. Written directly rather than through submit_work_report -
        # see the module docstring for what that call would wrongly drag in.
        status=WorkReportStatus.submitted,
        submitted_at=datetime.now(timezone.utc),
        origin=ReportOrigin.auto,
        report_mode=ReportMode.full_day.value,
        day_status=AUTO_WEEKEND_DAY_STATUS,
        total_minutes=0,
        # No actor: nobody authored this. `origin` is the source-of-truth
        # indicator; a NULL created_by is a consequence, never the test.
        created_by=None,
        updated_by=None,
    )
    db.add(report)
    try:
        db.flush()
        # One Full-Day period, identical to what a hand-entered full-day week_off
        # report gets from `service._sync_legacy_full_day_period`: work_fraction
        # 1.0, no location, not a legacy half day. Written here so an AUTO report
        # is structurally the same row shape as an employee one and no
        # period-reading consumer has to special-case it.
        db.add(
            WorkReportPeriod(
                report_id=report.id,
                day_part=DayPart.full_day.value,
                period_status=AUTO_WEEKEND_DAY_STATUS,
                location=None,
                work_fraction=DAY_PART_FRACTIONS[DayPart.full_day],
                is_legacy_half_day=False,
            )
        )
        if commit:
            db.commit()
        else:
            db.flush()
    except IntegrityError:
        # `work_reports_emp_date_uq` fired: a concurrent run (or the employee
        # themselves) took the slot between the SELECT above and this INSERT.
        # That is the constraint doing its job as the final duplicate guard, and
        # the correct outcome is "already exists", not a failure.
        db.rollback()
        logger.info(
            "auto_report.race_lost employee=%s date=%s", employee.id, report_date
        )
        return AutoReportOutcome(
            employee_id=employee.id, report_date=report_date, reason="report_exists"
        )

    logger.info(
        "auto_report.created employee=%s date=%s report=%s",
        employee.id,
        report_date,
        report.id,
    )
    return AutoReportOutcome(
        employee_id=employee.id,
        report_date=report_date,
        reason="created",
        report_id=report.id,
    )


def generate_auto_reports(
    db: Session | None = None,
    *,
    today: date | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    dates: list[date] | None = None,
) -> AutoReportRunResult:
    """Sweep recent dates and ensure an automatic report on every closed day.

    The swept range is `[today - lookback_days, today]` inclusive, so the run
    covers today (a Saturday morning run files that Saturday) and also re-covers
    the days behind it. Re-covering is free because the generator is idempotent,
    and it is what makes a late run, a duplicated run, a restart, or a failed
    previous run harmless: there is no cursor to lose and no catch-up mode.

    Safe from a Celery worker (opens its own session when `db` is omitted) and
    from a request handler (pass the request session). `dates` overrides the
    range outright and exists for tests and manual backfills.
    """
    owns_session = db is None
    db = db or SessionLocal()
    today = today or date.today()
    if dates is None:
        dates = [
            today - timedelta(days=offset)
            for offset in range(lookback_days, -1, -1)
        ]
    result = AutoReportRunResult(dates=list(dates))

    logger.info(
        "auto_report.started dates=%d from=%s to=%s",
        len(result.dates),
        result.dates[0] if result.dates else None,
        result.dates[-1] if result.dates else None,
    )
    try:
        if result.dates:
            non_working, working_overrides = load_calendar_overrides(
                db, min(result.dates), max(result.dates)
            )
            for target in result.dates:
                _generate_for_date(
                    db, target, non_working, working_overrides, result
                )
    finally:
        if owns_session:
            db.close()

    logger.info(
        "auto_report.completed dates=%d working_dates=%d considered=%d created=%d "
        "existing=%d failed=%d",
        len(result.dates),
        result.working_dates,
        result.employees_considered,
        result.created,
        result.skipped_existing,
        result.failed,
    )
    return result


def _generate_for_date(
    db: Session,
    target: date,
    non_working: set[date],
    working_overrides: set[date],
    result: AutoReportRunResult,
) -> None:
    """One date, all employees. Never raises: a single employee's failure is
    rolled back on its own and the sweep carries on, and because nothing was
    committed for them the next run picks them up again."""
    if is_working_day(
        target, non_working=non_working, working_overrides=working_overrides
    ):
        # Cheap exit before any employee query: the office was open, so no
        # automatic report exists to make for anybody on this date.
        result.working_dates += 1
        return

    employees = report_submitters(db, target)
    result.employees_considered += len(employees)
    if not employees:
        return

    # One SELECT for the whole date instead of one per employee. It is a
    # fast-path filter only - `ensure_auto_report` re-checks, and the unique
    # constraint is what actually guarantees the invariant.
    taken = existing_report_employee_ids(db, [e.id for e in employees], target)

    for employee in employees:
        if employee.id in taken:
            result.skipped_existing += 1
            result.outcomes.append(
                AutoReportOutcome(
                    employee_id=employee.id,
                    report_date=target,
                    reason="report_exists",
                )
            )
            continue
        try:
            outcome = ensure_auto_report(
                db,
                employee,
                target,
                non_working=non_working,
                working_overrides=working_overrides,
            )
        except Exception as exc:  # noqa: BLE001 - one employee must not stop the run
            db.rollback()
            result.failed += 1
            result.outcomes.append(
                AutoReportOutcome(
                    employee_id=employee.id,
                    report_date=target,
                    reason="error",
                    error=str(exc),
                )
            )
            logger.exception(
                "auto_report.failed employee=%s date=%s", employee.id, target
            )
            continue

        result.outcomes.append(outcome)
        if outcome.reason == "created":
            result.created += 1
        elif outcome.reason == "report_exists":
            # Only reachable via the unique-constraint race inside
            # `ensure_auto_report`; the `taken` fast path above caught the rest.
            result.skipped_existing += 1


# ---------------------------------------------------------------------------
# RECONCILIATION (Phase 3D) - a closed date becomes a working one
# ---------------------------------------------------------------------------
#
# SCOPE. Exactly `origin = auto AND day_status = week_off`, on a date the
# calendar now calls WORKING. Nothing else is ever looked at: an employee's own
# week_off report carries origin = 'employee', an automatic LEAVE report carries
# a different day_status, and both are therefore outside every query below.
#
# TWO OUTCOMES, decided per report by `is_untouched_auto_report`:
#
#   untouched -> DELETED. The row says nothing a person put there, and the date
#                is now an ordinary working day the employee must report on. The
#                delete relies on the existing DB cascades
#                (work_report_periods / work_report_tasks -> ON DELETE CASCADE),
#                so the children go with it.
#   touched   -> PRESERVED and RECLASSIFIED. Every field, period and task row is
#                kept; only the now-false `week_off` label is removed.
#
# NO REPLACEMENT IS EVER CREATED. Deleting frees the (employee, date) slot and
# the employee files their own report through the ordinary workflow; a date that
# goes the other way (working -> closed) is the 01:00 generator's job, not this
# function's. Reconciliation only ever removes a claim the calendar has
# withdrawn.

# The header fields a generated row leaves NULL. Any value in any of them is
# somebody's data, so the row is no longer untouched. `created_by`/`updated_by`
# are in the list because the generator writes neither and every write path a
# person can reach stamps `updated_by`.
_PRISTINE_NULL_FIELDS = (
    "location",
    "remarks",
    "query_text",
    "well_head_no",
    "pm_plant",
    "summary",
    "reviewed_by",
    "reviewed_at",
    "review_note",
    "edit_requested_at",
    "edit_request_note",
    "created_by",
    "updated_by",
)

# The Google-Form count fields. The generator sets none of them, so they hold the
# server default 0 (or None on a row not yet round-tripped through the DB); both
# read as "not filled in". Anything else is an employee's number.
_PRISTINE_ZERO_COUNT_FIELDS = (
    "task_list_count",
    "task_list_op_count",
    "maintenance_item_count",
    "maintenance_plan_count",
)


@dataclass(frozen=True)
class ReconcileOutcome:
    """What reconciliation did to one stale AUTO report."""

    report_id: uuid.UUID
    employee_id: uuid.UUID
    report_date: date
    # One of: "deleted", "reclassified".
    action: str


@dataclass
class AutoReconcileResult:
    dates: list[date] = field(default_factory=list)
    # Dates that are STILL non-working after the calendar change - nothing to
    # reconcile on those, which is the whole of the working -> closed direction.
    still_non_working: int = 0
    # In-scope AUTO week_off reports found on the now-working dates.
    examined: int = 0
    deleted: int = 0
    reclassified: int = 0
    outcomes: list[ReconcileOutcome] = field(default_factory=list)


def is_untouched_auto_report(db: Session, report: DailyWorkReport) -> bool:
    """Whether `report` still looks EXACTLY as the generator wrote it.

    The rule is conservative by construction: this returns True only for a row
    that matches the generated signature in every field, so anything unfamiliar -
    a field a later phase starts writing, a hand-made row, a legacy shape - falls
    through to False and is preserved. Deleting is the irreversible outcome, so
    doubt always resolves the other way.

    `total_minutes == 0` is NOT sufficient on its own and is never used alone:
    an author may edit an AUTO week_off report (see
    :func:`auto_report_author_editable`) and a week_off day drops task lines on
    every write path, so remarks, a query, a location or a count can all be typed
    onto the report while the total stays 0. The signature below therefore covers
    the whole row and its periods, not the minutes.

    The generated signature (`ensure_auto_report`):

        origin        = auto            status      = submitted (+ submitted_at)
        day_status    = week_off        report_mode = full_day
        total_minutes = 0               tasks       = none
        every field in _PRISTINE_NULL_FIELDS NULL
        every count in _PRISTINE_ZERO_COUNT_FIELDS 0 (or NULL)
        periods: at most one, and it is the generated Full-Day week_off period
    """
    if report.origin != ReportOrigin.auto:
        return False
    if report.day_status != AUTO_WEEKEND_DAY_STATUS:
        return False
    # Still born-submitted: an author edit reopens the report to draft and clears
    # `submitted_at`, so a draft (or a resubmitted, hence author-touched) row
    # never matches here.
    if report.status != WorkReportStatus.submitted or report.submitted_at is None:
        return False
    if report.report_mode != ReportMode.full_day.value:
        return False
    if report.total_minutes != 0:
        return False
    if any(getattr(report, name) is not None for name in _PRISTINE_NULL_FIELDS):
        return False
    if any(
        getattr(report, name) not in (None, 0)
        for name in _PRISTINE_ZERO_COUNT_FIELDS
    ):
        return False

    task_count = db.execute(
        select(func.count())
        .select_from(WorkReportTask)
        .where(WorkReportTask.report_id == report.id)
    ).scalar_one()
    if task_count:
        return False

    periods = db.execute(
        select(WorkReportPeriod).where(WorkReportPeriod.report_id == report.id)
    ).scalars().all()
    if len(periods) > 1:
        # Two periods means a split day, which no generated row has ever been.
        return False
    for period in periods:
        if (
            period.day_part != DayPart.full_day.value
            or period.period_status != AUTO_WEEKEND_DAY_STATUS
            or period.location is not None
            or period.remarks is not None
            or period.is_legacy_half_day
        ):
            return False
    return True


def _reclassify_auto_report(db: Session, report: DailyWorkReport) -> None:
    """Strip the now-false `week_off` label off a report that holds real data.

    Everything else is left exactly as it stands - tasks, periods, minutes,
    remarks, counts, `origin`. Only two things change:

      day_status -> NULL   the existing representation of a working day nobody
                           has classified yet. `create_work_report` treats a
                           period with no status as one that still owes
                           activities, which is precisely true here: the date is
                           a working day and this report does not yet account for
                           it. No new DayStatus is invented, and guessing
                           `work_at_office` would assert a fact nobody recorded.
      status     -> draft  only if it was `submitted`, and by the same reopen the
                           author's own edit performs (`update_work_report`):
                           `submitted_at` is cleared with it, keeping the two
                           moving together. A submitted report is a day declared
                           accounted for, which a status-less report with no
                           activities is not, and a draft is what puts the date
                           back in front of the employee.

    `origin` stays `auto`: the row really was generated, and that is permanent
    audit history, not a classification. Review / edit-request fields are not
    touched either - reconciliation is not a review and has no actor.
    """
    report.day_status = None
    if report.status == WorkReportStatus.submitted:
        report.status = WorkReportStatus.draft
        report.submitted_at = None
    # Keep the report's own periods coherent with the header. Only a period still
    # carrying the generated week_off status is cleared; a period the employee
    # gave a real status is left alone. work_fraction is untouched: a Full-Day
    # period is 1.0 with or without a status (`service._full_day_fraction`).
    db.execute(
        update(WorkReportPeriod)
        .where(
            WorkReportPeriod.report_id == report.id,
            WorkReportPeriod.period_status == AUTO_WEEKEND_DAY_STATUS,
        )
        .values(period_status=None)
    )
    db.add(report)


def reconcile_auto_reports_for_calendar_change(
    db: Session,
    dates: list[date] | set[date],
    *,
    commit: bool = True,
) -> AutoReconcileResult:
    """Remove or reclassify AUTO week-off reports on dates that are now WORKING.

    Call it with every date a calendar write may have re-classified - for an
    update that is the old AND the new event date. The direction does not have to
    be worked out by the caller: each date is re-read through
    `is_working_day` AFTER the change, and a date that is still non-working is
    skipped, so passing a date that moved the other way (or did not move at all)
    is free and does nothing.

    Idempotent. The first run leaves no in-scope row behind - a deleted report is
    gone and a reclassified one no longer carries `week_off` - so a second run
    selects nothing and writes nothing. Rows outside the scope are never read.

    `commit=False` keeps the work in the caller's transaction, which is how
    `calendar.service` uses it: the calendar row and its reconciliation commit
    together or not at all.
    """
    unique_dates = sorted(set(dates))
    result = AutoReconcileResult(dates=list(unique_dates))
    if not unique_dates:
        return result

    non_working, working_overrides = load_calendar_overrides(
        db, min(unique_dates), max(unique_dates)
    )
    now_working = [
        d
        for d in unique_dates
        if is_working_day(
            d, non_working=non_working, working_overrides=working_overrides
        )
    ]
    result.still_non_working = len(unique_dates) - len(now_working)
    if not now_working:
        return result

    stale = db.execute(
        select(DailyWorkReport).where(
            DailyWorkReport.report_date.in_(now_working),
            DailyWorkReport.origin == ReportOrigin.auto,
            DailyWorkReport.day_status == AUTO_WEEKEND_DAY_STATUS,
        )
    ).scalars().all()
    result.examined = len(stale)

    for report in stale:
        # Read off the row BEFORE it is deleted: the identifiers are what the
        # caller and the log line report, and a deleted instance is expired by
        # the flush below.
        report_id, employee_id = report.id, report.employee_id
        report_date = report.report_date
        if is_untouched_auto_report(db, report):
            # Nothing of anyone's in it. The periods (and any task rows, of which
            # there are none by definition here) go with it via the DB cascade.
            db.delete(report)
            action = "deleted"
            result.deleted += 1
        else:
            _reclassify_auto_report(db, report)
            action = "reclassified"
            result.reclassified += 1
        result.outcomes.append(
            ReconcileOutcome(
                report_id=report_id,
                employee_id=employee_id,
                report_date=report_date,
                action=action,
            )
        )
        logger.info(
            "auto_report.reconciled action=%s employee=%s date=%s report=%s",
            action,
            employee_id,
            report_date,
            report_id,
        )

    db.flush()
    if commit:
        db.commit()
    return result
