"""Migration 0069 must not change anybody's visible leave balance.

The one thing that would make this feature unsafe to ship is an employee opening
the Attendance page after the deploy and finding a different number. The opening
adjustment exists precisely to stop that, and this file proves it by replaying
the migration's backfill against a rebuilt pre-migration state.

WHY THE BACKFILL ADDS THE MONTH'S LEAVE BACK
============================================
`employee_leave_balances.available_leave` is a figure as of today: the month's
approved leave has ALREADY been subtracted from it by `leave/effects`. The ledger
will subtract that same leave again when it counts the month's `leave` attendance
rows. Seeding the raw figure would therefore charge every August absence twice.
Seeding `available_leave + this month's funded leave days` makes the derived
closing balance land back on `available_leave` exactly.

Also asserted here: `employee_leave_balances` and `employee_leave_balance_history`
survive the migration untouched. They are the rollback path, and the audit trail
is not something a schema change gets to discard.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.modules.attendance.models import AttendanceStatus
from app.modules.leave.models import LeaveStatus, LeaveType
from app.modules.leave_balances import ledger
from app.modules.leave_balances.models import (
    EmployeeLeaveAdjustment,
    EmployeeLeaveBalance,
    EmployeeLeaveBalanceHistory,
)

OPENING_MONTH = date(2026, 8, 1)


def _run_backfill(db) -> None:
    """Replay migration 0069's backfill statement verbatim.

    Loaded from the migration module itself, so if the SQL there changes and
    stops preserving balances, this test fails rather than silently testing a
    copy that no longer matches what production will run.
    """
    import importlib.util
    import pathlib

    path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0069_leave_allocation_ledger.py"
    )
    spec = importlib.util.spec_from_file_location("_mig_0069", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.OPENING_MONTH == OPENING_MONTH.isoformat()
    db.execute(module._BACKFILL.bindparams(opening_month=module.OPENING_MONTH))
    db.commit()


@pytest.fixture()
def pre_migration(db, make_employee, make_attendance):
    """Rebuild the shape of the production data as it stood before 0069.

    Three employees with balances, one of whom (the EMP225 case) has a leave day
    already marked in the opening month and therefore already deducted from the
    figure stored beside it.
    """
    people = {}
    for code, balance in (("EMP225", "2.50"), ("EM2160", "2.00"), ("MGR-001", "5.00")):
        emp = make_employee(employee_code=code, first_name=code, last_name="X")
        db.add(
            EmployeeLeaveBalance(
                employee_id=emp.id, available_leave=Decimal(balance)
            )
        )
        people[code] = emp
    db.commit()

    # EMP225's August leave: one funded day, already netted out of the 2.50.
    make_attendance(
        employee_id=people["EMP225"].id,
        attendance_date=date(2026, 8, 7),
        status=AttendanceStatus.leave,
    )
    return people


def test_the_backfill_reproduces_every_existing_balance_exactly(db, pre_migration):
    """2.50 / 2.00 / 5.00 before, and the same three after."""
    _run_backfill(db)

    expected = {"EMP225": "2.50", "EM2160": "2.00", "MGR-001": "5.00"}
    for code, value in expected.items():
        emp = pre_migration[code]
        assert ledger.closing_balance(db, emp.id, OPENING_MONTH) == Decimal(value), code


def test_the_opening_adjustment_adds_back_the_months_marked_leave(db, pre_migration):
    """EMP225: 2.50 stored + 1 day already marked = a 3.50 opening.

    Which then reads back as 3.50 + 0 allocation - 1 consumed = 2.50.
    """
    _run_backfill(db)
    emp = pre_migration["EMP225"]

    adjustment = (
        db.query(EmployeeLeaveAdjustment).filter_by(employee_id=emp.id).one()
    )
    assert adjustment.days == Decimal("3.50")
    assert adjustment.effective_month == OPENING_MONTH
    assert "Opening balance carried over" in adjustment.reason

    august = ledger.month_balance(db, emp.id, OPENING_MONTH)
    assert august.adjustment == Decimal("3.50")
    assert august.consumed == Decimal("1.00")
    assert august.allocation == Decimal("0.00")
    assert august.closing == Decimal("2.50")


def test_an_employee_with_no_leave_that_month_gets_their_figure_verbatim(
    db, pre_migration
):
    _run_backfill(db)
    emp = pre_migration["MGR-001"]
    adjustment = (
        db.query(EmployeeLeaveAdjustment).filter_by(employee_id=emp.id).one()
    )
    assert adjustment.days == Decimal("5.00")


def test_unpaid_days_are_not_added_back(
    db, make_employee, make_attendance, make_leave_request
):
    """An unpaid day was never deducted, so adding it back would invent a day."""
    emp = make_employee(employee_code="UNPAID-1", first_name="U", last_name="X")
    db.add(EmployeeLeaveBalance(employee_id=emp.id, available_leave=Decimal("4.00")))
    db.commit()
    make_leave_request(
        employee_id=emp.id,
        leave_type=LeaveType.unpaid,
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 10),
        status=LeaveStatus.approved,
    )
    make_attendance(
        employee_id=emp.id,
        attendance_date=date(2026, 8, 10),
        status=AttendanceStatus.leave,
    )

    _run_backfill(db)

    adjustment = db.query(EmployeeLeaveAdjustment).filter_by(employee_id=emp.id).one()
    assert adjustment.days == Decimal("4.00")
    assert ledger.closing_balance(db, emp.id, OPENING_MONTH) == Decimal("4.00")


def test_no_allocation_rows_are_invented(db, pre_migration):
    """`Leave/month` starts empty. Handing 2 d/month to everybody would grant
    leave nobody approved; the PM sets each value deliberately."""
    _run_backfill(db)
    count = db.execute(
        text("SELECT COUNT(*) FROM employee_leave_allocations")
    ).scalar_one()
    assert count == 0
    for emp in pre_migration.values():
        assert ledger.month_balance(db, emp.id, OPENING_MONTH).allocation == Decimal(
            "0.00"
        )


def test_an_employee_with_no_balance_row_gets_no_ledger(db, make_employee):
    """Nothing is invented for someone who never had a balance."""
    emp = make_employee(employee_code="FRESH-1", first_name="F", last_name="X")
    _run_backfill(db)
    assert db.query(EmployeeLeaveAdjustment).filter_by(employee_id=emp.id).count() == 0
    assert ledger.month_balance(db, emp.id, OPENING_MONTH).in_ledger is False


def test_the_snapshot_table_and_the_audit_trail_survive(db, pre_migration):
    """0069 drops nothing. The old balances stay readable as the rollback path,
    and every history row an employee's PM ever wrote is still there."""
    emp = pre_migration["EMP225"]
    db.add(
        EmployeeLeaveBalanceHistory(
            employee_id=emp.id,
            old_balance=Decimal("1.00"),
            new_balance=Decimal("2.50"),
            reason="available",
        )
    )
    db.commit()

    _run_backfill(db)

    snapshot = db.query(EmployeeLeaveBalance).filter_by(employee_id=emp.id).one()
    assert snapshot.available_leave == Decimal("2.50")
    assert db.query(EmployeeLeaveBalanceHistory).filter_by(employee_id=emp.id).count() == 1


def test_the_backfill_is_the_only_thing_that_seeds_a_ledger(db, pre_migration):
    """One opening row per employee - not one per month, and not one per read."""
    _run_backfill(db)
    total = db.execute(
        text("SELECT COUNT(*) FROM employee_leave_adjustments")
    ).scalar_one()
    assert total == len(pre_migration)
