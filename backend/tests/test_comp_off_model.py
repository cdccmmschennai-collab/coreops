"""Comp Off Phase 2 - database-level guarantees of `comp_off_requests`.

Model + migration only: no service, API or attendance behaviour exists yet, so
every test writes rows directly and asserts what the DATABASE accepts or
refuses.

    docker exec wms-backend-1 pytest tests/test_comp_off_model.py
"""
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.modules.comp_off.models import CompOffRequest, CompOffStatus

SUN = date(2027, 3, 14)      # a Sunday - a typical worked day
SUN_2 = date(2027, 3, 21)
MON = date(2027, 3, 15)      # the day off
TUE = date(2027, 3, 16)


@pytest.fixture()
def emp(make_employee):
    return make_employee(employee_code="EMPCO1")


@pytest.fixture()
def reviewer(make_employee):
    return make_employee(employee_code="MGRCO1")


def _add(db, employee_id, worked=SUN, off=MON, status=CompOffStatus.pending, **kw):
    row = CompOffRequest(
        employee_id=employee_id, worked_date=worked, off_date=off, status=status, **kw
    )
    db.add(row)
    db.flush()
    return row


def _decided(reviewer):
    return {"manager_id": reviewer.id, "reviewed_at": datetime.now(timezone.utc)}


def _refused(db, **kw):
    with pytest.raises(IntegrityError):
        _add(db, **kw)
    db.rollback()


# ── shape and defaults ─────────────────────────────────────────────────────

def test_a_pending_request_is_stored_with_defaults(db, emp):
    db.add(CompOffRequest(employee_id=emp.id, worked_date=SUN, off_date=MON,
                          reason="Worked Sunday shutdown"))
    db.commit()
    row = db.query(CompOffRequest).one()
    assert row.status == CompOffStatus.pending
    assert row.id is not None and row.created_at is not None and row.updated_at is not None
    assert row.manager_id is None and row.reviewed_at is None


def test_the_migration_created_the_expected_constraints_and_indexes(db):
    insp = inspect(db.get_bind())
    checks = {c["name"] for c in insp.get_check_constraints("comp_off_requests")}
    assert {"comp_off_dates_differ", "comp_off_decision_consistent"} <= checks
    indexes = {i["name"]: i for i in insp.get_indexes("comp_off_requests")}
    for name in ("comp_off_live_worked_date_uq", "comp_off_live_off_date_uq"):
        assert indexes[name]["unique"]
    assert db.execute(text("SELECT enum_range(NULL::comp_off_status)::text")).scalar() == (
        "{pending,approved,rejected,cancelled}"
    )


# ── row-level checks ───────────────────────────────────────────────────────

def test_worked_date_must_differ_from_off_date(db, emp):
    _refused(db, employee_id=emp.id, worked=SUN, off=SUN)


def test_the_employee_must_exist(db, emp):
    _refused(db, employee_id=uuid.uuid4())


def test_an_employee_with_requests_cannot_be_hard_deleted(db, emp):
    _add(db, emp.id)
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM employees WHERE id = :id"), {"id": emp.id})
        db.flush()
    db.rollback()


def test_pending_cannot_carry_a_decision(db, emp, reviewer):
    _refused(db, employee_id=emp.id, **_decided(reviewer))
    _refused(db, employee_id=emp.id, manager_id=reviewer.id)


@pytest.mark.parametrize("status", [CompOffStatus.approved, CompOffStatus.rejected])
def test_a_decision_must_say_when_it_was_made(db, emp, reviewer, status):
    _refused(db, employee_id=emp.id, status=status, manager_id=reviewer.id)
    row = _add(db, emp.id, status=status, manager_comment="ok", **_decided(reviewer))
    assert row.status == status


def test_a_reviewer_removed_later_does_not_invalidate_the_decision(db, emp, reviewer):
    row = _add(db, emp.id, status=CompOffStatus.approved, **_decided(reviewer))
    db.commit()
    db.execute(text("DELETE FROM employees WHERE id = :id"), {"id": reviewer.id})
    db.commit()
    db.refresh(row)
    assert row.manager_id is None and row.reviewed_at is not None


def test_cancelled_is_allowed_with_or_without_a_prior_review(db, emp, reviewer):
    _add(db, emp.id, worked=SUN, off=MON, status=CompOffStatus.cancelled)
    _add(db, emp.id, worked=SUN, off=MON, status=CompOffStatus.cancelled,
         **_decided(reviewer))
    db.commit()


# ── live-request uniqueness ────────────────────────────────────────────────

@pytest.mark.parametrize("second_status", [CompOffStatus.pending, CompOffStatus.approved])
def test_one_live_request_per_worked_date(db, emp, reviewer, second_status):
    _add(db, emp.id, worked=SUN, off=MON)
    extra = _decided(reviewer) if second_status == CompOffStatus.approved else {}
    _refused(db, employee_id=emp.id, worked=SUN, off=TUE, status=second_status, **extra)


@pytest.mark.parametrize("second_status", [CompOffStatus.pending, CompOffStatus.approved])
def test_one_live_request_per_off_date(db, emp, reviewer, second_status):
    _add(db, emp.id, worked=SUN, off=MON)
    extra = _decided(reviewer) if second_status == CompOffStatus.approved else {}
    _refused(db, employee_id=emp.id, worked=SUN_2, off=MON, status=second_status, **extra)


def test_rejected_and_cancelled_history_does_not_block_a_new_request(db, emp, reviewer):
    _add(db, emp.id, status=CompOffStatus.rejected, manager_comment="No evidence",
         **_decided(reviewer))
    _add(db, emp.id, status=CompOffStatus.cancelled)
    _add(db, emp.id, status=CompOffStatus.cancelled)
    _add(db, emp.id)  # a fresh live request on the very same dates
    db.commit()
    assert db.query(CompOffRequest).count() == 4


def test_uniqueness_is_per_employee(db, emp, reviewer):
    _add(db, emp.id)
    _add(db, reviewer.id)  # another employee, same dates
    db.commit()


def test_the_same_row_can_move_through_its_lifecycle(db, emp, reviewer):
    row = _add(db, emp.id)
    db.commit()
    row.status = CompOffStatus.approved
    row.manager_id, row.reviewed_at = reviewer.id, datetime.now(timezone.utc)
    db.commit()
    row.status = CompOffStatus.cancelled
    db.commit()
    # Cancelling frees both dates for a new live request.
    _add(db, emp.id)
    db.commit()
