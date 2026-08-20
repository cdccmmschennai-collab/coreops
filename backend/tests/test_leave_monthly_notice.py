"""Phase 5: automatic monthly accrual, and the monthly balance notification.

Two halves, and the split matters:

  ACCRUAL      is not a job. Sections 1-8 assert that the monthly allocation,
               the carry-forward and the PM correction all fall out of
               `ledger.month_balance` on a plain read - nothing is scheduled,
               nothing is incremented, and nothing had to run for September to
               open with August's closing figure.
  NOTIFICATION is a job, and sections 9-17 assert what it says, who gets it,
               that it says it once, and that one failure does not silence
               everybody else.

Dates are pinned to 2027 so nothing collides with the real "today".
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.modules.attendance.models import AttendanceStatus
from app.modules.employees.models import EmployeeStatus
from app.modules.leave_balances import ledger
from app.modules.leave_balances import service as lb_service
from app.modules.leave_balances.schemas import LeaveAllocationUpdate
from app.modules.notifications.models import Notification
from app.modules.users.models import UserRole
from app.reminders.leave_balance import dispatcher
from app.reminders.leave_balance.dispatcher import (
    NOTICE_TYPE,
    run_monthly_leave_balance_notices,
)
from app.reminders.leave_balance.message import build_message, format_days

JAN = date(2027, 1, 1)
FEB = date(2027, 2, 1)
MAR = date(2027, 3, 1)
APR = date(2027, 4, 1)
AUG = date(2027, 8, 1)
SEP = date(2027, 9, 1)
OCT = date(2027, 10, 1)


def _closing(db, employee_id, month) -> Decimal:
    return ledger.closing_balance(db, employee_id, month)


@pytest.fixture()
def make_staff(make_user, make_employee):
    """An employee with a login - the only kind that can be notified.

    Returns the Employee; the User is reachable through `employee.user_id`.
    """
    counter = {"n": 0}

    def _make(
        *,
        first_name="Santhosh",
        last_name="Kumar",
        user_active=True,
        status=EmployeeStatus.active,
    ):
        counter["n"] += 1
        n = counter["n"]
        user = make_user(
            email=f"staff{n}@example.com",
            role=UserRole.employee,
            is_active=user_active,
        )
        return make_employee(
            employee_code=f"NOTICE-{n}",
            first_name=first_name,
            last_name=last_name,
            user_id=user.id,
            status=status,
        )

    return _make


def _notifications(db, employee=None) -> list[Notification]:
    stmt = select(Notification).where(Notification.type == NOTICE_TYPE)
    if employee is not None:
        stmt = stmt.where(Notification.user_id == employee.user_id)
    return list(db.execute(stmt).scalars())


# ======================================================================
# 1-3. Different employees, different monthly allocations
# ======================================================================

@pytest.mark.parametrize("per_month", [1, 2, 3])
def test_allocation_accrues_every_month_at_the_employees_own_rate(
    db, make_employee, make_leave_allocation, per_month
):
    """One rate is configured once; every later month grants it again.

    No row is written per month and no job runs - January is `per_month`,
    February is twice that, March three times, purely because the fold visits
    each month once.
    """
    emp = make_employee(employee_code=f"RATE-{per_month}")
    make_leave_allocation(
        employee_id=emp.id, effective_from=JAN, monthly_days=per_month
    )

    assert _closing(db, emp.id, JAN) == Decimal(per_month).quantize(Decimal("0.01"))
    assert _closing(db, emp.id, FEB) == Decimal(per_month * 2).quantize(Decimal("0.01"))
    assert _closing(db, emp.id, MAR) == Decimal(per_month * 3).quantize(Decimal("0.01"))


def test_three_employees_keep_three_different_rates(
    db, make_employee, make_leave_allocation
):
    """The rate belongs to the employee. Nothing global is consulted."""
    rates = {}
    for code, per_month in (("A", 1), ("B", 2), ("C", 3)):
        emp = make_employee(employee_code=f"MULTI-{code}")
        make_leave_allocation(
            employee_id=emp.id, effective_from=JAN, monthly_days=per_month
        )
        rates[code] = emp

    assert _closing(db, rates["A"].id, MAR) == Decimal("3.00")
    assert _closing(db, rates["B"].id, MAR) == Decimal("6.00")
    assert _closing(db, rates["C"].id, MAR) == Decimal("9.00")


# ======================================================================
# 4. Carry-forward - the worked example from the brief
# ======================================================================

def test_unused_leave_carries_forward_into_the_next_month(
    db, make_employee, make_leave_allocation, make_leave_adjustment, make_attendance
):
    """August 1.5 -> September 2.5 -> October 4.5, on 2 days/month.

        August     alloc 2, carry 0,   used 0.5   closing 1.5
        September  alloc 2, carry 1.5, used 1     closing 2.5
        October    alloc 2, carry 2.5, used 0     closing 4.5

    August's half day is expressed as a -0.5 adjustment: CoreOps marks whole
    leave days on the calendar, and half a day is a correction.
    """
    emp = make_employee(employee_code="CARRY-1")
    make_leave_allocation(employee_id=emp.id, effective_from=AUG, monthly_days=2)
    make_leave_adjustment(
        employee_id=emp.id, effective_month=AUG, days="-0.5", reason="Half day"
    )
    make_attendance(
        employee_id=emp.id,
        attendance_date=date(2027, 9, 14),
        status=AttendanceStatus.leave,
    )

    assert _closing(db, emp.id, AUG) == Decimal("1.50")
    assert _closing(db, emp.id, SEP) == Decimal("2.50")
    assert _closing(db, emp.id, OCT) == Decimal("4.50")

    # And September's opening IS August's closing - not a second figure kept
    # somewhere and hopefully in step.
    september = ledger.month_balance(db, emp.id, SEP)
    assert september.carry_forward == Decimal("1.50")


def test_reading_a_month_repeatedly_never_accrues_twice(
    db, make_employee, make_leave_allocation
):
    """The month transition needs no action, and reading is pure.

    Asking for September ten times - which is what a page refresh does - answers
    the same number ten times.
    """
    emp = make_employee(employee_code="PURE-1")
    make_leave_allocation(employee_id=emp.id, effective_from=AUG, monthly_days=2)

    answers = {_closing(db, emp.id, SEP) for _ in range(10)}
    assert answers == {Decimal("4.00")}


# ======================================================================
# 5. Effective-dated allocation
# ======================================================================

def test_a_rate_change_in_march_does_not_rewrite_january_and_february(
    db, make_employee, make_leave_allocation
):
    """January 1, February 1, March 2 - the brief's example, exactly.

        January   1  (closing 1)
        February  1  (closing 2)
        March     2  (closing 4)
        April     2  (closing 6)
    """
    emp = make_employee(employee_code="EFF-1")
    make_leave_allocation(employee_id=emp.id, effective_from=JAN, monthly_days=1)
    make_leave_allocation(employee_id=emp.id, effective_from=MAR, monthly_days=2)

    assert ledger.month_balance(db, emp.id, JAN).allocation == Decimal("1.00")
    assert ledger.month_balance(db, emp.id, FEB).allocation == Decimal("1.00")
    assert ledger.month_balance(db, emp.id, MAR).allocation == Decimal("2.00")

    assert _closing(db, emp.id, JAN) == Decimal("1.00")
    assert _closing(db, emp.id, FEB) == Decimal("2.00")
    assert _closing(db, emp.id, MAR) == Decimal("4.00")
    assert _closing(db, emp.id, APR) == Decimal("6.00")


def test_one_allocation_row_per_effective_month(db, make_user, make_employee):
    """Re-saving the same effective month updates that row - it never stacks a
    second allocation onto the month, so a month cannot accrue twice."""
    pm = make_user("pm-alloc@example.com", role=UserRole.project_manager)
    emp = make_employee(employee_code="EFF-2")

    for days in (1, 3):
        lb_service.set_allocation(
            db,
            pm,
            emp.id,
            LeaveAllocationUpdate(monthly_days=days, effective_from=JAN),
        )

    assert lb_service.list_allocations(db, emp.id).total == 1
    assert ledger.month_balance(db, emp.id, JAN).allocation == Decimal("3.00")


# ======================================================================
# 6. PM correction + next-month carry
# ======================================================================

def test_a_pm_correction_carries_into_october_and_october_still_accrues(
    db, make_employee, make_leave_allocation, make_leave_adjustment, make_attendance
):
    """The brief's scenario, end to end.

        September  carry 1.5, alloc 2, used 1  -> automatic closing 2.5
        PM correction +1                        -> September closing 3.5
        October    carry 3.5, alloc 2, used 0  -> closing 5.5

    The correction survives the month boundary, and it did NOT become a change
    to Leave/month: October's allocation is still 2.
    """
    emp = make_employee(employee_code="CORR-1")
    make_leave_allocation(employee_id=emp.id, effective_from=AUG, monthly_days=2)
    make_leave_adjustment(
        employee_id=emp.id, effective_month=AUG, days="-0.5", reason="Half day"
    )
    make_attendance(
        employee_id=emp.id,
        attendance_date=date(2027, 9, 14),
        status=AttendanceStatus.leave,
    )
    assert _closing(db, emp.id, SEP) == Decimal("2.50")

    make_leave_adjustment(
        employee_id=emp.id, effective_month=SEP, days="1", reason="PM correction"
    )

    assert _closing(db, emp.id, SEP) == Decimal("3.50")
    october = ledger.month_balance(db, emp.id, OCT)
    assert october.carry_forward == Decimal("3.50")
    assert october.allocation == Decimal("2.00")
    assert october.closing == Decimal("5.50")


# ======================================================================
# 7. No Leave/month configured
# ======================================================================

def test_no_allocation_accrues_nothing_and_carries_the_balance_untouched(
    db, make_employee, make_leave_adjustment
):
    """allocation = 0. No default is invented, and the existing balance stays."""
    emp = make_employee(employee_code="NOALLOC-1")
    make_leave_adjustment(
        employee_id=emp.id, effective_month=AUG, days="3", reason="Opening balance"
    )

    for month in (AUG, SEP, OCT):
        assert ledger.month_balance(db, emp.id, month).allocation == Decimal("0.00")
        assert _closing(db, emp.id, month) == Decimal("3.00")


# ======================================================================
# 8. Negative balances
# ======================================================================

def test_a_negative_balance_is_reported_and_still_accrues(
    db, make_employee, make_leave_allocation, make_leave_adjustment
):
    """Nothing is clamped and nothing is blocked because the figure is below 0."""
    emp = make_employee(employee_code="NEG-1")
    make_leave_allocation(employee_id=emp.id, effective_from=AUG, monthly_days=1)
    make_leave_adjustment(
        employee_id=emp.id, effective_month=AUG, days="-4", reason="Loss of pay"
    )

    assert _closing(db, emp.id, AUG) == Decimal("-3.00")
    # September still receives its allocation on top of the negative carry.
    assert _closing(db, emp.id, SEP) == Decimal("-2.00")
    assert _closing(db, emp.id, OCT) == Decimal("-1.00")


# ======================================================================
# 9-12. The notification: generated, named, worded, and correct
# ======================================================================

def test_the_monthly_notification_is_generated(
    db, make_staff, make_leave_allocation
):
    emp = make_staff()
    make_leave_allocation(employee_id=emp.id, effective_from=AUG, monthly_days=2)

    result = run_monthly_leave_balance_notices(db=db, month=SEP)

    assert result.month == SEP
    assert result.sent == 1
    rows = _notifications(db, emp)
    assert len(rows) == 1
    assert rows[0].title == "Leave Balance Update"
    assert rows[0].user_id == emp.user_id


def test_the_message_names_the_employee_and_quotes_the_ledger_balance(
    db, make_staff, make_leave_allocation, make_attendance
):
    """September: carry 2 + alloc 2 - 0 used = 4. The message says 4, because it
    asked the ledger rather than adding anything up itself."""
    emp = make_staff(first_name="Santhosh", last_name="Kumar")
    make_leave_allocation(employee_id=emp.id, effective_from=AUG, monthly_days=2)

    run_monthly_leave_balance_notices(db=db, month=SEP)

    message = _notifications(db, emp)[0].message
    assert message == "Santhosh Kumar, you have 4 available leave days."
    assert message == build_message(emp.full_name, _closing(db, emp.id, SEP))


def test_the_message_reports_a_fractional_balance_as_it_is(
    db, make_staff, make_leave_allocation, make_leave_adjustment
):
    emp = make_staff(first_name="John", last_name="Doe")
    make_leave_allocation(employee_id=emp.id, effective_from=SEP, monthly_days=2)
    make_leave_adjustment(
        employee_id=emp.id, effective_month=SEP, days="-0.5", reason="Half day"
    )

    run_monthly_leave_balance_notices(db=db, month=SEP)

    assert (
        _notifications(db, emp)[0].message
        == "John Doe, you have 1.5 available leave days."
    )


def test_the_message_reports_a_negative_balance_without_hiding_it(
    db, make_staff, make_leave_adjustment
):
    emp = make_staff(first_name="John", last_name="Doe")
    make_leave_adjustment(
        employee_id=emp.id, effective_month=SEP, days="-1", reason="Loss of pay"
    )

    run_monthly_leave_balance_notices(db=db, month=SEP)

    assert (
        _notifications(db, emp)[0].message
        == "John Doe, you have -1 available leave days."
    )


# ---------- 9. grammar (pure) ----------------------------------------------

@pytest.mark.parametrize(
    ("days", "expected"),
    [
        ("1", "Santhosh Kumar, you have 1 available leave day."),
        ("1.00", "Santhosh Kumar, you have 1 available leave day."),
        ("4", "Santhosh Kumar, you have 4 available leave days."),
        ("1.50", "Santhosh Kumar, you have 1.5 available leave days."),
        ("0", "Santhosh Kumar, you have 0 available leave days."),
        ("-1", "Santhosh Kumar, you have -1 available leave days."),
        ("2", "Santhosh Kumar, you have 2 available leave days."),
    ],
)
def test_singular_only_for_exactly_one_day(days, expected):
    assert build_message("Santhosh Kumar", Decimal(days)) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("4.00", "4"), ("1.50", "1.5"), ("0.00", "0"), ("-1.00", "-1"), ("100", "100")],
)
def test_a_balance_prints_without_trailing_zeros(value, expected):
    assert format_days(Decimal(value)) == expected


# ======================================================================
# 13 + 17. Idempotency
# ======================================================================

def test_running_the_job_twice_does_not_duplicate_the_notification(
    db, make_staff, make_leave_allocation
):
    emp = make_staff()
    make_leave_allocation(employee_id=emp.id, effective_from=AUG, monthly_days=2)

    first = run_monthly_leave_balance_notices(db=db, month=SEP)
    second = run_monthly_leave_balance_notices(db=db, month=SEP)
    third = run_monthly_leave_balance_notices(db=db, month=SEP)

    assert (first.sent, first.already_sent) == (1, 0)
    assert (second.sent, second.already_sent) == (0, 1)
    assert (third.sent, third.already_sent) == (0, 1)
    assert len(_notifications(db, emp)) == 1


def test_a_read_notification_still_counts_as_sent(
    db, make_staff, make_leave_allocation
):
    """De-duplication does not depend on the employee leaving it unread."""
    emp = make_staff()
    make_leave_allocation(employee_id=emp.id, effective_from=AUG, monthly_days=2)
    run_monthly_leave_balance_notices(db=db, month=SEP)

    row = _notifications(db, emp)[0]
    row.is_read = True
    db.commit()

    assert run_monthly_leave_balance_notices(db=db, month=SEP).sent == 0
    assert len(_notifications(db, emp)) == 1


def test_each_month_gets_its_own_notification(
    db, make_staff, make_leave_allocation
):
    """Idempotency is per MONTH, not per employee - October must still arrive."""
    emp = make_staff()
    make_leave_allocation(employee_id=emp.id, effective_from=AUG, monthly_days=2)

    run_monthly_leave_balance_notices(db=db, month=SEP)
    run_monthly_leave_balance_notices(db=db, month=OCT)

    messages = sorted(n.message for n in _notifications(db, emp))
    assert messages == [
        "Santhosh Kumar, you have 4 available leave days.",
        "Santhosh Kumar, you have 6 available leave days.",
    ]


# ======================================================================
# 14. Who is eligible
# ======================================================================

def test_employees_who_cannot_receive_notifications_are_excluded(
    db, make_staff, make_employee, make_leave_allocation, make_leave_adjustment
):
    """Inactive login, exited employee, soft-deleted employee, and an employee
    with no login at all - none of them are notified. The active one is."""
    active = make_staff(first_name="Active", last_name="One")
    inactive_login = make_staff(
        first_name="Inactive", last_name="Login", user_active=False
    )
    exited = make_staff(
        first_name="Exited", last_name="One", status=EmployeeStatus.exited
    )
    deleted = make_staff(first_name="Deleted", last_name="One")
    no_login = make_employee(employee_code="NOLOGIN-1")

    everyone = [active, inactive_login, exited, deleted, no_login]
    for emp in everyone:
        make_leave_allocation(employee_id=emp.id, effective_from=AUG, monthly_days=2)

    deleted.deleted_at = datetime.now(timezone.utc)
    db.commit()

    result = run_monthly_leave_balance_notices(db=db, month=SEP)

    assert result.eligible == 1
    assert result.sent == 1
    assert len(_notifications(db, active)) == 1
    for emp in (inactive_login, exited, deleted):
        assert _notifications(db, emp) == []


def test_a_pm_configured_allocation_alone_makes_an_employee_participate(
    db, make_staff, make_leave_allocation
):
    """A PM-set Leave/month is enough. No legacy balance row is involved.

    The employee has NO `employee_leave_balances` row, no opening adjustment and
    no history of any kind - only the allocation the PM just set. Migration
    0069's opening balances are one way into the ledger, not the way in, and
    nothing in the accrual or the notification consults the frozen pre-ledger
    table (`EmployeeLeaveBalance` is referenced nowhere outside its own model).

        PM sets Leave/month = 2, effective September 2026

        September  ledger begins here, alloc 2, carry 0, used 0  -> closing 2

    Dated 2026 rather than the file's 2027 because it is the exact scenario the
    business rule was stated in.
    """
    september = date(2026, 9, 1)
    emp = make_staff(first_name="Santhosh", last_name="Kumar")
    make_leave_allocation(
        employee_id=emp.id, effective_from=september, monthly_days=2
    )

    # 1. The allocation alone starts the ledger.
    assert ledger.ledger_start(db, emp.id) == september
    assert emp.id in ledger.employees_with_ledger(db, september)

    # 2. September is calculated automatically, with no job and no stored row.
    balance = ledger.month_balance(db, emp.id, september)
    assert balance.in_ledger is True
    assert balance.ledger_start == september
    assert balance.carry_forward == Decimal("0.00")
    assert balance.allocation == Decimal("2.00")
    assert balance.closing == Decimal("2.00")

    # 3. And the employee is in September's notification audience.
    assert emp.id in {e.id for e in dispatcher.eligible_employees(db, september)}
    result = run_monthly_leave_balance_notices(db=db, month=september)
    assert (result.eligible, result.sent) == (1, 1)
    assert (
        _notifications(db, emp)[0].message
        == "Santhosh Kumar, you have 2 available leave days."
    )

    # 4. October carries September forward and accrues again - no legacy row,
    #    no manual step, no second notification for September.
    assert _closing(db, emp.id, date(2026, 10, 1)) == Decimal("4.00")


def test_an_employee_with_no_ledger_is_not_notified(db, make_staff):
    """No allocation and no adjustment means no balance to state - the same
    reason the Attendance card shows "-" rather than "0d"."""
    make_staff()

    result = run_monthly_leave_balance_notices(db=db, month=SEP)

    assert result.eligible == 0
    assert result.sent == 0
    assert _notifications(db) == []


# ======================================================================
# 15. Failure isolation
# ======================================================================

def test_one_failure_does_not_stop_the_other_employees(
    db, monkeypatch, make_staff, make_leave_allocation
):
    """And the failure is not recorded as sent, so the next run retries it."""
    first = make_staff(first_name="First", last_name="Employee")
    boom = make_staff(first_name="Broken", last_name="Employee")
    last = make_staff(first_name="Last", last_name="Employee")
    for emp in (first, boom, last):
        make_leave_allocation(employee_id=emp.id, effective_from=AUG, monthly_days=2)

    real_create = dispatcher.create_notification

    def _explode(db_, **kwargs):
        if kwargs["user_id"] == boom.user_id:
            raise RuntimeError("delivery failed")
        return real_create(db_, **kwargs)

    monkeypatch.setattr(dispatcher, "create_notification", _explode)
    result = run_monthly_leave_balance_notices(db=db, month=SEP)

    assert result.sent == 2
    assert result.failed == 1
    assert len(_notifications(db, first)) == 1
    assert len(_notifications(db, last)) == 1
    assert _notifications(db, boom) == []

    # The retry: nothing was committed for the failed employee, so they are
    # still unsent - and the two who succeeded are not sent a second time.
    monkeypatch.undo()
    retry = run_monthly_leave_balance_notices(db=db, month=SEP)

    assert (retry.sent, retry.already_sent) == (1, 2)
    assert len(_notifications(db, boom)) == 1


# ======================================================================
# 16. The month boundary is Chennai's, not the server's
# ======================================================================

def test_the_month_is_the_chennai_business_month(db, monkeypatch, make_staff,
                                                 make_leave_allocation):
    """A server at 19:00 UTC on 31 August is already in September in Chennai,
    and the run must be September's - not August's."""

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = datetime(2027, 8, 31, 19, 0, tzinfo=timezone.utc)
            return instant.astimezone(tz) if tz else instant

    monkeypatch.setattr(lb_service, "datetime", _FrozenDatetime)
    assert lb_service.business_today() == date(2027, 9, 1)

    emp = make_staff()
    make_leave_allocation(employee_id=emp.id, effective_from=AUG, monthly_days=2)

    result = run_monthly_leave_balance_notices(db=db)

    assert result.month == SEP
    # September's balance (2 carried + 2 accrued), not August's 2.
    assert (
        _notifications(db, emp)[0].message
        == "Santhosh Kumar, you have 4 available leave days."
    )


def test_the_business_timezone_is_asia_kolkata():
    """The constant the month boundary hangs on. If this changes, every month
    key in the system moves."""
    assert lb_service.BUSINESS_TZ == ZoneInfo("Asia/Kolkata")


# ======================================================================
# 18. The scheduler's job is to TELL, never to ACCRUE
# ======================================================================

def test_beat_carries_the_notification_and_no_leave_accrual_task():
    """The only leave-related thing on the schedule is the notification.

    Guards the line this design rests on: if an "add the monthly leave" task
    ever appears on beat, leave would be granted by a process that can run
    twice, miss a month, or run against a stale balance - and the ledger's
    guarantees would quietly stop being guarantees.
    """
    from app.core.celery_app import (
        DAILY_REPORT_REMINDER_TASK,
        LEAVE_BALANCE_NOTICE_TASK,
        celery_app,
    )

    scheduled = {
        name: entry["task"]
        for name, entry in celery_app.conf.beat_schedule.items()
    }
    assert scheduled == {
        "daily-report-reminder": DAILY_REPORT_REMINDER_TASK,
        "monthly-leave-balance-notice": LEAVE_BALANCE_NOTICE_TASK,
    }


def test_leave_accrues_with_no_scheduler_and_the_job_never_moves_a_balance(
    db, make_staff, make_leave_allocation
):
    """Two halves of the same rule.

    FIRST: no Celery worker and no beat exist in this process, nothing is
    enqueued, and August/September/October still accrue 2, 4, 6 - because
    accrual is a fold performed on read, not something a scheduler does. Stop
    the scheduler in production and the balances are unaffected; only the
    monthly message stops arriving.

    SECOND: running the notification job does not change the figure it reports.
    It reads the ledger and writes a `notifications` row - nothing else - so the
    balance before the run, after the run, and after a second run is one number.
    """
    emp = make_staff()
    make_leave_allocation(employee_id=emp.id, effective_from=AUG, monthly_days=2)

    assert _closing(db, emp.id, AUG) == Decimal("2.00")
    assert _closing(db, emp.id, SEP) == Decimal("4.00")
    assert _closing(db, emp.id, OCT) == Decimal("6.00")

    run_monthly_leave_balance_notices(db=db, month=SEP)
    run_monthly_leave_balance_notices(db=db, month=SEP)

    assert _closing(db, emp.id, AUG) == Decimal("2.00")
    assert _closing(db, emp.id, SEP) == Decimal("4.00")
    assert _closing(db, emp.id, OCT) == Decimal("6.00")
