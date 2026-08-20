"""The month-aware leave balance API, and the two PM decisions behind it.

Everything here goes through HTTP, because the point of Phase 3 is that the
rules hold against a direct API call and not merely against the UI. Authorisation
in particular is asserted by calling the endpoints as an employee, never by
reading the dependency list.

Months are pinned to 2027 so nothing collides with the real "today", except where
a test is specifically about the default (which must be the current Chennai
business month).
"""
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from app.modules.attendance.models import AttendanceStatus
from app.modules.leave_balances.models import (
    EmployeeLeaveAdjustment,
    EmployeeLeaveAllocation,
    EmployeeLeaveBalanceHistory,
)
from app.modules.users.models import UserRole

API = "/api/v1/leave-balances"

JAN = date(2027, 1, 1)
FEB = date(2027, 2, 1)
MAR = date(2027, 3, 1)

AUG = date(2027, 8, 1)
SEP = date(2027, 9, 1)
OCT = date(2027, 10, 1)


@pytest.fixture()
def team(make_user, make_employee):
    """A project manager and an employee, each with a login."""
    mu = make_user("pm@lb.com", role=UserRole.project_manager)
    mgr = make_employee(
        employee_code="PM-1", first_name="Priya", last_name="M", user_id=mu.id
    )
    eu = make_user("emp@lb.com", role=UserRole.employee)
    emp = make_employee(
        employee_code="EMP225",
        first_name="Santhosh",
        last_name="Kumar",
        user_id=eu.id,
        manager_id=mgr.id,
    )
    return {"manager": mgr, "employee": emp}


def _pm(login):
    return login("pm@lb.com")


def _emp(login):
    return login("emp@lb.com")


def _me(client, login, month=None):
    url = f"{API}/me" + (f"?month={month.isoformat()}" if month else "")
    res = client.get(url, headers=_emp(login))
    assert res.status_code == 200, res.text
    return res.json()


def _allocate(client, login, employee_id, monthly_days, effective_from, note=None):
    return client.put(
        f"{API}/{employee_id}/allocation",
        headers=_pm(login),
        json={
            "monthly_days": monthly_days,
            "effective_from": effective_from.isoformat(),
            "note": note,
        },
    )


def _correct(client, login, employee_id, target, reason="Correction", month=None):
    body = {"available_leave": target, "reason": reason}
    if month is not None:
        body["month"] = month.isoformat()
    return client.post(f"{API}/{employee_id}", headers=_pm(login), json=body)


# ======================================================================
# Month-aware reads
# ======================================================================

def test_each_month_reports_its_own_balance(client, login, team, make_attendance):
    """August 2, September 3, October 5 - on 2 d/month with one day taken."""
    emp = team["employee"]
    assert _allocate(client, login, emp.id, 2, AUG).status_code == 200
    make_attendance(
        employee_id=emp.id,
        attendance_date=date(2027, 9, 14),
        status=AttendanceStatus.leave,
    )

    assert _me(client, login, AUG)["available_leave"] == 2.0
    assert _me(client, login, SEP)["available_leave"] == 3.0
    assert _me(client, login, OCT)["available_leave"] == 5.0


def test_the_response_shows_its_working(client, login, team, make_attendance):
    """Every term of the formula, so a wrong total can be diagnosed from the
    payload instead of by reading the ledger."""
    emp = team["employee"]
    _allocate(client, login, emp.id, 2, AUG)
    make_attendance(
        employee_id=emp.id,
        attendance_date=date(2027, 9, 14),
        status=AttendanceStatus.leave,
    )
    _correct(client, login, emp.id, 4.5, month=SEP)

    body = _me(client, login, SEP)
    assert body["month"] == SEP.isoformat()
    assert body["carry_forward"] == 2.0
    assert body["monthly_allocation"] == 2.0
    assert body["adjustment"] == 1.5
    assert body["consumed"] == 1.0
    assert body["available_leave"] == 4.5
    assert body["in_ledger"] is True
    assert body["ledger_start_month"] == AUG.isoformat()


def test_august_is_identical_after_visiting_september(client, login, team):
    """August -> September -> August. The whole reason this phase exists."""
    emp = team["employee"]
    _allocate(client, login, emp.id, 2, AUG)

    first = _me(client, login, AUG)
    _me(client, login, SEP)
    _me(client, login, OCT)
    again = _me(client, login, AUG)
    assert again == first


def test_reading_a_month_never_accrues_it(client, login, team, db):
    """Ten reads, one answer, and not a single row written.

    This is the duplicate-accrual guarantee stated as a test: if the allocation
    were applied on read, the tenth call would differ from the first and the
    adjustment table would have grown.
    """
    emp = team["employee"]
    _allocate(client, login, emp.id, 2, AUG)
    rows = text("SELECT COUNT(*) FROM employee_leave_adjustments")
    before = db.execute(rows).scalar_one()

    answers = {_me(client, login, AUG)["available_leave"] for _ in range(10)}
    assert answers == {2.0}

    assert db.execute(rows).scalar_one() == before


def test_any_date_in_the_month_resolves_to_that_month(client, login, team):
    """A calendar month, never a rolling 30 days: the 1st and the 31st agree."""
    emp = team["employee"]
    _allocate(client, login, emp.id, 2, AUG)
    first = _me(client, login, date(2027, 8, 1))
    last = _me(client, login, date(2027, 8, 31))
    assert first == last
    assert first["month"] == AUG.isoformat()


def test_omitting_the_month_uses_the_current_business_month(client, login, team):
    """Not the browser's month, and not UTC - the Chennai business month."""
    _allocate(client, login, team["employee"].id, 2, date(2020, 1, 1))
    ist_today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    assert _me(client, login)["month"] == ist_today.replace(day=1).isoformat()


def test_a_month_before_the_ledger_reports_not_in_ledger(client, login, team):
    """Distinct from a zero balance - there is nothing to state."""
    _allocate(client, login, team["employee"].id, 2, SEP)
    body = _me(client, login, AUG)
    assert body["in_ledger"] is False
    assert body["available_leave"] == 0.0
    assert body["ledger_start_month"] == SEP.isoformat()


def test_an_invalid_month_is_rejected(client, login, team):
    res = client.get(f"{API}/me?month=not-a-date", headers=_emp(login))
    assert res.status_code == 422, res.text


# ======================================================================
# The manager list
# ======================================================================

def test_the_list_reports_every_employee_for_the_requested_month(
    client, login, team
):
    emp, mgr = team["employee"], team["manager"]
    _allocate(client, login, emp.id, 2, AUG)
    _allocate(client, login, mgr.id, 1, AUG)

    res = client.get(f"{API}?month={SEP.isoformat()}", headers=_pm(login))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["month"] == SEP.isoformat()

    by_code = {i["employee_code"]: i for i in body["items"]}
    assert by_code["EMP225"]["available_leave"] == 4.0
    assert by_code["EMP225"]["monthly_allocation"] == 2.0
    assert by_code["PM-1"]["available_leave"] == 2.0
    assert by_code["PM-1"]["monthly_allocation"] == 1.0


def test_the_list_carries_the_name_and_code_the_table_shows(client, login, team):
    res = client.get(f"{API}?q=EMP225", headers=_pm(login))
    item = res.json()["items"][0]
    assert item["employee_code"] == "EMP225"
    assert item["employee_name"] == "Santhosh Kumar"


def test_last_updated_moves_when_a_manager_acts(client, login, team):
    """It means "when did a manager last set this", so it is null until one does."""
    emp = team["employee"]
    res = client.get(f"{API}?q=EMP225", headers=_pm(login))
    assert res.json()["items"][0]["last_updated"] is None

    _allocate(client, login, emp.id, 2, AUG)
    res = client.get(f"{API}?q=EMP225", headers=_pm(login))
    assert res.json()["items"][0]["last_updated"] is not None


# ======================================================================
# PM allocation
# ======================================================================

@pytest.mark.parametrize("rate,expected", [(1, 3.0), (2, 6.0), (3, 9.0)])
def test_the_pm_can_set_one_two_or_three_days_a_month(
    client, login, team, rate, expected
):
    assert _allocate(client, login, team["employee"].id, rate, AUG).status_code == 200
    assert _me(client, login, OCT)["available_leave"] == expected


def test_a_fractional_allocation_is_accepted(client, login, team):
    """0.5 d/month - not hard-coded to whole days."""
    assert _allocate(client, login, team["employee"].id, 0.5, AUG).status_code == 200
    assert _me(client, login, OCT)["available_leave"] == 1.5


def test_changing_the_rate_in_march_leaves_january_and_february_alone(
    client, login, team
):
    """The historical-correctness case, over HTTP."""
    emp = team["employee"]
    _allocate(client, login, emp.id, 1, JAN)
    _allocate(client, login, emp.id, 2, MAR)

    assert _me(client, login, JAN)["monthly_allocation"] == 1.0
    assert _me(client, login, FEB)["monthly_allocation"] == 1.0
    assert _me(client, login, MAR)["monthly_allocation"] == 2.0
    # 1 + 1 + 2
    assert _me(client, login, MAR)["available_leave"] == 4.0


def test_resaving_the_same_effective_month_updates_that_one_row(
    client, login, team, db
):
    """A correction to a decision, not a second competing rate for one month."""
    emp = team["employee"]
    _allocate(client, login, emp.id, 2, AUG)
    _allocate(client, login, emp.id, 3, AUG)

    rows = db.query(EmployeeLeaveAllocation).filter_by(employee_id=emp.id).all()
    assert len(rows) == 1
    assert rows[0].monthly_days == Decimal("3.00")
    assert _me(client, login, AUG)["available_leave"] == 3.0


def test_the_allocation_list_shows_every_rate_newest_first(client, login, team):
    emp = team["employee"]
    _allocate(client, login, emp.id, 1, JAN)
    _allocate(client, login, emp.id, 2, MAR, note="Off probation")

    res = client.get(f"{API}/{emp.id}/allocations", headers=_pm(login))
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert [i["effective_from"] for i in items] == [MAR.isoformat(), JAN.isoformat()]
    assert items[0]["monthly_days"] == 2.0
    assert items[0]["note"] == "Off probation"


def test_an_effective_date_mid_month_is_refused(client, login, team):
    """Silently snapping the 15th to the 1st would grant a fortnight nobody
    approved, so it is rejected instead."""
    res = _allocate(client, login, team["employee"].id, 2, date(2027, 8, 15))
    assert res.status_code == 422, res.text


def test_a_negative_allocation_is_refused(client, login, team):
    """An allocation is a grant. A deduction is an adjustment."""
    res = _allocate(client, login, team["employee"].id, -1, AUG)
    assert res.status_code == 422, res.text


def test_allocation_for_an_unknown_employee_is_404(client, login, team):
    import uuid as _uuid

    res = _allocate(client, login, _uuid.uuid4(), 2, AUG)
    assert res.status_code == 404, res.text


# ======================================================================
# PM correction
# ======================================================================

def test_a_correction_is_stored_as_the_difference_not_the_target(
    client, login, team, db
):
    """The manager types 4; the ledger records +2 on top of the automatic 2.

    That is what lets the allocation survive: had the target been stored, the
    monthly accrual underneath would have had to be overwritten.
    """
    emp = team["employee"]
    _allocate(client, login, emp.id, 2, AUG)
    res = _correct(client, login, emp.id, 4.0, reason="Goodwill day", month=AUG)
    assert res.status_code == 200, res.text

    body = res.json()
    assert body["available_leave"] == 4.0
    assert body["monthly_allocation"] == 2.0
    assert body["adjustment"] == 2.0
    row = db.query(EmployeeLeaveAdjustment).filter_by(employee_id=emp.id).one()
    assert row.days == Decimal("2.00")
    assert row.effective_month == AUG
    assert row.reason == "Goodwill day"


def test_a_negative_correction_reduces_the_month(client, login, team):
    emp = team["employee"]
    _allocate(client, login, emp.id, 2, AUG)
    _correct(client, login, emp.id, 1.5, reason="Taken in lieu", month=AUG)
    assert _me(client, login, AUG)["available_leave"] == 1.5


def test_a_correction_does_not_stop_the_next_month_accruing(client, login, team):
    """The brief's central PM-correction rule, over HTTP."""
    emp = team["employee"]
    _allocate(client, login, emp.id, 2, SEP)
    _correct(client, login, emp.id, 1.0, reason="Correction", month=SEP)

    assert _me(client, login, SEP)["available_leave"] == 1.0
    # October still receives its own 2 days on top of the corrected September.
    assert _me(client, login, OCT)["available_leave"] == 3.0
    assert _me(client, login, OCT)["monthly_allocation"] == 2.0


def test_a_correction_does_not_change_the_allocation(client, login, team, db):
    emp = team["employee"]
    _allocate(client, login, emp.id, 2, AUG)
    _correct(client, login, emp.id, 10.0, month=AUG)

    rows = db.query(EmployeeLeaveAllocation).filter_by(employee_id=emp.id).all()
    assert len(rows) == 1
    assert rows[0].monthly_days == Decimal("2.00")


def test_a_correction_only_affects_the_month_it_was_made_for(client, login, team):
    emp = team["employee"]
    _allocate(client, login, emp.id, 2, AUG)
    _correct(client, login, emp.id, 10.0, month=SEP)
    assert _me(client, login, AUG)["available_leave"] == 2.0
    assert _me(client, login, SEP)["available_leave"] == 10.0


def test_two_corrections_to_one_month_both_survive(client, login, team, db):
    """Neither manager's decision is silently overwritten, and each keeps its own
    reason and author in the audit trail."""
    emp = team["employee"]
    _allocate(client, login, emp.id, 2, AUG)
    _correct(client, login, emp.id, 3.0, reason="First", month=AUG)
    _correct(client, login, emp.id, 5.0, reason="Second", month=AUG)
    rows = db.query(EmployeeLeaveAdjustment).filter_by(employee_id=emp.id).all()
    assert sorted(r.days for r in rows) == [Decimal("1.00"), Decimal("2.00")]
    assert _me(client, login, AUG)["available_leave"] == 5.0

    reasons = {
        h.reason
        for h in db.query(EmployeeLeaveBalanceHistory).filter_by(employee_id=emp.id)
    }
    assert reasons == {"First", "Second"}


def test_every_correction_writes_the_existing_history_row(client, login, team, db):
    """Reused, not replaced: the same audit trail the Leave Balance tab shows."""
    emp = team["employee"]
    _allocate(client, login, emp.id, 2, AUG)
    _correct(client, login, emp.id, 3.5, reason="Comp off granted", month=AUG)

    entry = db.query(EmployeeLeaveBalanceHistory).filter_by(employee_id=emp.id).one()
    assert (entry.old_balance, entry.new_balance) == (Decimal("2.00"), Decimal("3.50"))
    assert entry.reason == "Comp off granted"
    assert entry.updated_by is not None

    res = client.get(f"{API}/{emp.id}/history", headers=_pm(login))
    assert res.status_code == 200, res.text
    item = res.json()["items"][0]
    assert item["reason"] == "Comp off granted"
    assert item["updated_by_name"] == "Priya M"


def test_a_correction_notifies_the_employee(client, login, team):
    emp = team["employee"]
    _allocate(client, login, emp.id, 2, AUG)
    _correct(client, login, emp.id, 5.0, reason="Comp off", month=AUG)

    notifs = client.get("/api/v1/notifications", headers=_emp(login)).json()["items"]
    balance_notifs = [n for n in notifs if n["type"] == "leave_balance_updated"]
    assert len(balance_notifs) == 1
    assert "2 to 5" in balance_notifs[0]["message"]
    assert "Comp off" in balance_notifs[0]["message"]


def test_a_correction_that_changes_nothing_notifies_nobody(client, login, team, db):
    """...but is still recorded: the manager acted, and said why."""
    emp = team["employee"]
    _allocate(client, login, emp.id, 2, AUG)
    _correct(client, login, emp.id, 2.0, reason="Checked, no change", month=AUG)
    assert db.query(EmployeeLeaveAdjustment).filter_by(employee_id=emp.id).count() == 0
    assert (
        db.query(EmployeeLeaveBalanceHistory).filter_by(employee_id=emp.id).count() == 1
    )
    notifs = client.get("/api/v1/notifications", headers=_emp(login)).json()["items"]
    assert not [n for n in notifs if n["type"] == "leave_balance_updated"]


def test_a_correction_requires_a_reason(client, login, team):
    res = client.post(
        f"{API}/{team['employee'].id}",
        headers=_pm(login),
        json={"available_leave": 3.0, "reason": ""},
    )
    assert res.status_code == 422, res.text


def test_a_correction_month_must_be_a_month_start(client, login, team):
    res = _correct(client, login, team["employee"].id, 3.0, month=date(2027, 8, 9))
    assert res.status_code == 422, res.text


# ======================================================================
# Negative balances
# ======================================================================

def test_a_negative_balance_can_be_set_and_is_reported(client, login, team):
    """Loss-of-pay. Nothing clamps it, at any layer."""
    emp = team["employee"]
    res = _correct(client, login, emp.id, -1.0, reason="LOP", month=AUG)
    assert res.status_code == 200, res.text
    assert res.json()["available_leave"] == -1.0
    assert _me(client, login, AUG)["available_leave"] == -1.0


def test_a_negative_balance_carries_forward_as_a_deficit(client, login, team):
    emp = team["employee"]
    _allocate(client, login, emp.id, 1, AUG)
    _correct(client, login, emp.id, -2.0, reason="LOP", month=AUG)
    assert _me(client, login, SEP)["available_leave"] == -1.0
    assert _me(client, login, OCT)["available_leave"] == 0.0


# ======================================================================
# No allocation
# ======================================================================

def test_no_allocation_invents_no_leave(client, login, team):
    """An employee the PM has not configured accrues nothing - the system does
    not guess 1, 2 or 3 days on their behalf."""
    body = _me(client, login, AUG)
    assert body["monthly_allocation"] == 0.0
    assert body["available_leave"] == 0.0
    assert body["in_ledger"] is False


def test_an_opening_balance_without_an_allocation_just_carries_forward(
    client, login, team
):
    """The state migration 0069 left every existing employee in: they keep what
    they had, month after month, until the PM sets a `Leave/month`."""
    emp = team["employee"]
    _correct(client, login, emp.id, 2.5, reason="Opening balance", month=AUG)

    assert _me(client, login, AUG)["available_leave"] == 2.5
    assert _me(client, login, SEP)["available_leave"] == 2.5
    assert _me(client, login, OCT)["available_leave"] == 2.5
    assert _me(client, login, OCT)["monthly_allocation"] == 0.0


# ======================================================================
# Authorisation
# ======================================================================

def test_an_employee_cannot_set_an_allocation(client, login, team):
    res = client.put(
        f"{API}/{team['employee'].id}/allocation",
        headers=_emp(login),
        json={"monthly_days": 30, "effective_from": AUG.isoformat()},
    )
    assert res.status_code == 403, res.text


def test_an_employee_cannot_correct_a_balance(client, login, team):
    res = client.post(
        f"{API}/{team['employee'].id}",
        headers=_emp(login),
        json={"available_leave": 99.0, "reason": "mine now"},
    )
    assert res.status_code == 403, res.text


def test_an_employee_cannot_list_everybody(client, login, team):
    assert client.get(API, headers=_emp(login)).status_code == 403


def test_an_employee_cannot_read_another_employees_balance(client, login, team):
    res = client.get(f"{API}/{team['manager'].id}", headers=_emp(login))
    assert res.status_code == 403, res.text


def test_an_employee_cannot_read_allocations_or_history(client, login, team):
    emp_id = team["employee"].id
    assert client.get(f"{API}/{emp_id}/allocations", headers=_emp(login)).status_code == 403
    assert client.get(f"{API}/{emp_id}/history", headers=_emp(login)).status_code == 403


def test_an_employee_can_read_their_own_balance(client, login, team):
    assert client.get(f"{API}/me", headers=_emp(login)).status_code == 200


def test_the_endpoints_require_authentication(client, team):
    assert client.get(f"{API}/me").status_code == 401
    assert client.get(API).status_code == 401


# ======================================================================
# Leave consumption, through the API
# ======================================================================

def test_approved_leave_reduces_the_month_it_falls_in(
    client, login, team, make_leave_request
):
    """The KPI figure and the approval move together, with nothing stored."""
    emp = team["employee"]
    _allocate(client, login, emp.id, 3, AUG)
    req = make_leave_request(
        employee_id=emp.id, start_date=date(2027, 8, 4), end_date=date(2027, 8, 5)
    )
    res = client.post(
        f"/api/v1/leave-requests/{req.id}/approve", headers=_pm(login), json={}
    )
    assert res.status_code == 200, res.text

    august = _me(client, login, AUG)
    assert august["consumed"] == 2.0
    assert august["available_leave"] == 1.0
    # ...and September opens on what August closed with, plus its own allocation.
    assert _me(client, login, SEP)["available_leave"] == 4.0


def test_a_rejected_leave_consumes_nothing(client, login, team, make_leave_request):
    emp = team["employee"]
    _allocate(client, login, emp.id, 3, AUG)
    req = make_leave_request(
        employee_id=emp.id, start_date=date(2027, 8, 4), end_date=date(2027, 8, 5)
    )
    client.post(
        f"/api/v1/leave-requests/{req.id}/reject", headers=_pm(login), json={}
    )
    assert _me(client, login, AUG)["consumed"] == 0.0
    assert _me(client, login, AUG)["available_leave"] == 3.0


def test_cancelling_an_approved_leave_restores_the_month(
    client, login, team, make_leave_request
):
    emp = team["employee"]
    _allocate(client, login, emp.id, 3, AUG)
    req = make_leave_request(
        employee_id=emp.id, start_date=date(2027, 8, 4), end_date=date(2027, 8, 5)
    )
    client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=_pm(login), json={})
    assert _me(client, login, AUG)["available_leave"] == 1.0

    client.post(
        f"/api/v1/leave-requests/{req.id}/request-cancellation", headers=_emp(login)
    )
    res = client.post(
        f"/api/v1/leave-requests/{req.id}/approve-cancellation", headers=_pm(login)
    )
    assert res.status_code == 200, res.text
    assert _me(client, login, AUG)["available_leave"] == 3.0


def test_a_company_half_day_does_not_consume_leave(
    client, login, team, make_attendance
):
    """The 2026-08-14 case: a company-wide half day is half a WORKING day."""
    emp = team["employee"]
    _allocate(client, login, emp.id, 2, AUG)
    make_attendance(
        employee_id=emp.id,
        attendance_date=date(2027, 8, 13),
        status=AttendanceStatus.half_day,
    )
    body = _me(client, login, AUG)
    assert body["consumed"] == 0.0
    assert body["available_leave"] == 2.0


def test_leave_can_still_be_approved_from_a_zero_or_negative_balance_when_unpaid(
    client, login, team, make_leave_request
):
    """Eligibility is unchanged: unpaid leave was never subject to the balance
    guard, and a zero or negative balance must not start blocking it."""
    from app.modules.leave.models import LeaveType

    emp = team["employee"]
    _correct(client, login, emp.id, -1.0, reason="LOP", month=AUG)
    req = make_leave_request(
        employee_id=emp.id,
        leave_type=LeaveType.unpaid,
        start_date=date(2027, 8, 4),
        end_date=date(2027, 8, 5),
    )
    res = client.post(
        f"/api/v1/leave-requests/{req.id}/approve", headers=_pm(login), json={}
    )
    assert res.status_code == 200, res.text
    # The days are marked, and the negative balance is untouched by them.
    assert _me(client, login, AUG)["available_leave"] == -1.0
