"""The monthly leave balance notification run.

    "Santhosh Kumar, you have 4 available leave days."

WHAT THIS JOB DOES NOT DO
=========================
It does not accrue anything. There is no `balance += monthly_days` here and
there is nowhere for one to go: the balance is `ledger.month_balance`, folded
from the allocation and adjustment rows on every read, and September already
opens with August's closing figure the first time anybody asks - job or no job,
notification or no notification. Turning this task off would not cost an
employee a single day. All it does is TELL the employee a number the ledger
already answers.

That is also why the figure cannot disagree with the Attendance card: both call
`ledger.month_balance` for the same month. Nothing here computes
`previous + allocation`.

WHICH MONTH
===========
The current CHENNAI business month, via `leave_balances.service.resolve_month`
- the same helper the API resolves `?month=` with. The server's own timezone is
never consulted, so a worker running in UTC at 19:00 on 31 August is already
into September's month, exactly as the employee reading the page in Chennai is.

IDEMPOTENCY
===========
One notification per (employee, month), enforced by a DETERMINISTIC id rather
than by a run timestamp: `_notice_key` hashes the employee and the month into a
uuid5 that is stored as the notification's `entity_id`. Running the job twice -
or twenty times - finds the row already there and sends nothing. "When did this
last run" is never asked, because it cannot answer for an employee who was
created since, or for one whose send failed on the previous attempt.

No new table and no migration: `notifications` already carries
(type, entity_type, entity_id), and the model's own docstring puts de-duplication
in the service layer rather than in a DB constraint. This follows that rule.

RUN IT DAILY, NOT ONCE A MONTH
==============================
Beat fires this every morning, and the month key is what makes that correct
rather than spammy: the first run of a new month sends, every later run in that
month is a no-op. A monthly-only trigger would silently skip the whole month if
the worker happened to be down on the 1st, would never reach an employee whose
ledger begins mid-month, and would give a failed send no second chance. Here a
failure simply retries tomorrow, because a failure writes no row.

FAILURE IS PER EMPLOYEE
=======================
Each employee is committed on their own. One employee's error rolls back that
employee's transaction only - the run continues, and because nothing was
committed for them, they are still "unsent" and the next run will try again. A
send is never recorded unless the row it wrote is committed.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.leave_balances import ledger
from app.modules.leave_balances.service import resolve_month
from app.modules.notifications.models import Notification
from app.modules.notifications.service import create_notification
from app.modules.users.models import User
from app.reminders.leave_balance.message import TITLE, build_message

logger = logging.getLogger("coreops.reminders.leave_balance")

# The notification's kind, as the notification centre and the frontend see it.
NOTICE_TYPE = "leave_balance_monthly"
# The "entity" this notification is about: one employee's one month. Not the
# employee - two months are two notifications, and that is the whole point.
NOTICE_ENTITY_TYPE = "leave_balance_month"
# Fixed namespace for the uuid5 key below. Constant forever: changing it would
# make every past month look unsent and re-notify the entire company.
NOTICE_NAMESPACE = uuid.UUID("2f0f0d5a-6b3f-5a2e-9c41-8d2b7e6a1f30")

# Where the employee lands from the notification - the page that shows the
# balance the message quotes.
NOTICE_TARGET_URL = "/attendance"


def notice_key(employee_id: uuid.UUID, month: date) -> uuid.UUID:
    """The idempotency id for one employee's one month.

    Derived, not random, so the same (employee, month) always produces the same
    id and "has this been sent" is a lookup rather than a guess.
    """
    return uuid.uuid5(NOTICE_NAMESPACE, f"{employee_id}:{ledger.month_start(month)}")


@dataclass
class NoticeOutcome:
    employee_id: uuid.UUID
    employee_name: str
    balance: Decimal | None = None
    sent: bool = False
    already_sent: bool = False
    error: str | None = None


@dataclass
class MonthlyNoticeResult:
    month: date
    eligible: int = 0
    sent: int = 0
    already_sent: int = 0
    skipped_no_ledger: int = 0
    failed: int = 0
    outcomes: list[NoticeOutcome] = field(default_factory=list)


def eligible_employees(db: Session, month: date) -> list[Employee]:
    """Everyone who should be told their balance for `month`.

    Three filters, none of them invented here:

      the ledger      `employees_with_ledger` - an employee whose ledger has not
                      begun has no balance to state, which is exactly why the
                      Attendance card shows "-" for them rather than "0d".
      the employee    not soft-deleted, and `status == active` - the same pair
                      the daily report reminder selects reporting employees by.
      the login       linked to a User that is active and not soft-deleted - the
                      same test `calendar/service.py` applies before notifying
                      the company. An employee with no login is dropped by the
                      join: a notification needs somebody to deliver it to.
    """
    ids = ledger.employees_with_ledger(db, month)
    if not ids:
        return []
    return list(
        db.execute(
            select(Employee)
            .join(User, Employee.user_id == User.id)
            .where(
                Employee.id.in_(ids),
                Employee.deleted_at.is_(None),
                Employee.status == EmployeeStatus.active,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
            .order_by(Employee.employee_code)
        )
        .scalars()
        .all()
    )


def _already_notified(
    db: Session, keys: list[uuid.UUID]
) -> set[uuid.UUID]:
    """Which of these (employee, month) keys already have a notification row.

    Deliberately NOT filtered by `resolved_at` or `is_read`: an employee who has
    read and dismissed August's message has still been told, and must not be told
    again.
    """
    if not keys:
        return set()
    return set(
        db.execute(
            select(Notification.entity_id).where(
                Notification.type == NOTICE_TYPE,
                Notification.entity_type == NOTICE_ENTITY_TYPE,
                Notification.entity_id.in_(keys),
            )
        ).scalars()
    )


def run_monthly_leave_balance_notices(
    *, db: Session | None = None, month: date | None = None
) -> MonthlyNoticeResult:
    """Notify every eligible employee of their balance for the current month.

    Safe from a Celery worker (opens its own session when `db` is omitted) and
    from a request handler (pass the request session). `month` is for tests and
    the debug trigger; production passes nothing and gets the Chennai business
    month.
    """
    owns_session = db is None
    db = db or SessionLocal()
    key = resolve_month(month)
    result = MonthlyNoticeResult(month=key)

    logger.info("leave_notice.started month=%s", key)
    try:
        employees = eligible_employees(db, key)
        result.eligible = len(employees)
        sent_keys = _already_notified(
            db, [notice_key(emp.id, key) for emp in employees]
        )
        for emp in employees:
            _process_employee(db, emp, key, sent_keys, result)
    finally:
        if owns_session:
            db.close()

    logger.info(
        "leave_notice.completed month=%s eligible=%d sent=%d already=%d "
        "no_ledger=%d failed=%d",
        key,
        result.eligible,
        result.sent,
        result.already_sent,
        result.skipped_no_ledger,
        result.failed,
    )
    return result


def _process_employee(
    db: Session,
    emp: Employee,
    month: date,
    sent_keys: set[uuid.UUID],
    result: MonthlyNoticeResult,
) -> None:
    """One employee, in its own transaction. Never raises."""
    key = notice_key(emp.id, month)
    if key in sent_keys:
        result.already_sent += 1
        result.outcomes.append(
            NoticeOutcome(
                employee_id=emp.id, employee_name=emp.full_name, already_sent=True
            )
        )
        return

    try:
        # THE authoritative figure - the same call the Leave Balance API and the
        # Attendance KPI make. Not recomputed, not adjusted, not rounded again.
        balance = ledger.month_balance(db, emp.id, month)
        if not balance.in_ledger:
            # Belt-and-braces: `eligible_employees` already excluded these.
            result.skipped_no_ledger += 1
            result.outcomes.append(
                NoticeOutcome(employee_id=emp.id, employee_name=emp.full_name)
            )
            return

        create_notification(
            db,
            user_id=emp.user_id,
            type_=NOTICE_TYPE,
            title=TITLE,
            message=build_message(emp.full_name, balance.closing),
            entity_type=NOTICE_ENTITY_TYPE,
            entity_id=key,
            target_url=NOTICE_TARGET_URL,
        )
        db.commit()
        sent_keys.add(key)
        result.sent += 1
        result.outcomes.append(
            NoticeOutcome(
                employee_id=emp.id,
                employee_name=emp.full_name,
                balance=balance.closing,
                sent=True,
            )
        )
        logger.info(
            "leave_notice.sent employee=%s month=%s balance=%s",
            emp.employee_code,
            month,
            balance.closing,
        )
    except Exception as exc:  # noqa: BLE001 - one employee must not stop the run
        # Nothing was committed, so this employee stays unsent and tomorrow's run
        # picks them up again.
        db.rollback()
        result.failed += 1
        result.outcomes.append(
            NoticeOutcome(
                employee_id=emp.id, employee_name=emp.full_name, error=str(exc)
            )
        )
        logger.exception(
            "leave_notice.failed employee=%s month=%s", emp.employee_code, month
        )
