"""Leave cannot be taken for a day the biometric device settled as worked.

The gap this closes: the existing guard read `attendance_records` only, so a day
with a full punch pair but NO official record sailed through - the employee
filed, the PM approved, and `effects.py` wrote a Leave row underneath punches
that were still there. The calendar then showed Leave on a day the device said
the person worked a full shift, with no warning anywhere.

What is deliberately NOT blocked: an unsettled day. One punch, or a day whose
shift could not be compared against, means the evidence did not establish
anything, and refusing leave on that would be a guess - exactly the invented
cause `classification.py` exists to avoid.

Dates are pinned to known weekdays so a run on a Saturday cannot change how many
working days a range contains.

    docker exec wms-backend-1 pytest tests/test_leave_biometric_block.py
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.modules.biometric.models import BiometricEmployeeMapping, BiometricPunch
from app.modules.biometric.service import settled_present_days
from app.modules.leave.models import LeaveRequest, LeaveStatus
from app.modules.leave_balances import ledger
from app.modules.leave_balances.models import EmployeeLeaveAdjustment
from app.modules.users.models import UserRole

API = "/api/v1/leave-requests"

IST_OFFSET = timedelta(hours=5, minutes=30)

# 2027-03-08 is a Monday; 2027-03-13/14 are the Saturday and Sunday after it.
# That Saturday is the SECOND of March 2027, so it is genuinely non-working under
# the company calendar - which is what
# `test_a_punch_on_a_non_working_day_does_not_block_the_range` is about. (The
# week starting 2027-03-01 ends on a FIRST Saturday, an ordinary working day.)
MON = date(2027, 3, 8)
TUE = MON + timedelta(days=1)
SAT = MON + timedelta(days=5)
SUN = MON + timedelta(days=6)

CODE = "9001"


def ist(day: date, hh: int, mm: int) -> datetime:
    """An Asia/Kolkata wall-clock instant on `day`, stored as aware UTC."""
    return datetime(
        day.year, day.month, day.day, hh, mm, tzinfo=timezone(IST_OFFSET)
    )


@pytest.fixture()
def team(make_user, make_employee):
    mu = make_user("mgr@x.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MGR", user_id=mu.id)
    eu = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="EMP069", user_id=eu.id, manager_id=mgr.id)
    return {"manager": mgr, "employee": emp}


@pytest.fixture()
def mapped(db, team):
    """The employee's device code, mapped - attribution is via the mapping table,
    never `biometric_punches.employee_id`, exactly as the real backfill is."""
    db.add(
        BiometricEmployeeMapping(
            provider="easytime",
            external_employee_code=CODE,
            employee_id=team["employee"].id,
            is_active=True,
        )
    )
    db.commit()
    return team["employee"]


@pytest.fixture()
def punch(db):
    counter = {"n": 0}

    def _make(when: datetime, *, code: str = CODE) -> BiometricPunch:
        counter["n"] += 1
        db.add(
            BiometricPunch(
                provider="easytime",
                external_transaction_id=f"txn-{counter['n']}",
                external_employee_code=code,
                employee_id=None,
                punch_time=when,
                received_at=datetime.now(timezone.utc),
                raw_punch_state="0",
            )
        )
        db.commit()

    return _make


def _full_day(punch, day: date) -> None:
    """The 12 Aug shape the report described: 09:10 in, 17:54 out."""
    punch(ist(day, 9, 10))
    punch(ist(day, 17, 54))


def _file(client, login, start: date, end: date, leave_type="unpaid"):
    return client.post(
        API,
        headers=login("emp@x.com"),
        json={
            "leave_type": leave_type,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "reason": "Family function",
        },
    )


# ── the block, at filing time ──────────────────────────────────────────────

def test_a_fully_punched_day_cannot_be_requested_as_leave(
    client, login, team, mapped, punch
):
    """The reported case: punches on the day, no attendance record, leave filed."""
    _full_day(punch, MON)
    res = _file(client, login, MON, MON)
    assert res.status_code == 422, res.text
    message = res.json()["error"]["message"]
    assert "biometric record" in message
    assert "8 March 2027" in message
    # The punch window is named, so the employee can recognise (or dispute) it.
    assert "09:10 AM" in message and "05:54 PM" in message


def test_one_punch_does_not_block_a_leave_request(client, login, team, mapped, punch):
    """`incomplete` is not `present`. One sighting settles nothing, so it must
    not cost the employee their ability to file."""
    punch(ist(MON, 9, 10))
    res = _file(client, login, MON, MON)
    assert res.status_code == 201, res.text


def test_a_day_with_no_punches_is_unaffected(client, login, team, mapped):
    res = _file(client, login, MON, TUE)
    assert res.status_code == 201, res.text


def test_only_the_punched_day_of_a_range_is_named(client, login, team, mapped, punch):
    _full_day(punch, TUE)
    res = _file(client, login, MON, TUE)
    assert res.status_code == 422, res.text
    message = res.json()["error"]["message"]
    assert "9 March 2027" in message
    assert "8 March 2027" not in message


def test_a_punch_on_a_non_working_day_does_not_block_the_range(
    client, login, team, mapped, punch
):
    """A weekend punch costs nothing and marks nothing - an approval would never
    touch that day - so it must not refuse the whole week."""
    _full_day(punch, SAT)
    _full_day(punch, SUN)
    res = _file(client, login, MON, SUN)
    assert res.status_code == 201, res.text


def test_editing_a_request_onto_a_punched_day_is_refused(
    client, login, team, mapped, punch
):
    created = _file(client, login, MON, MON)
    assert created.status_code == 201, created.text
    _full_day(punch, TUE)
    res = client.patch(
        f"{API}/{created.json()['id']}",
        headers=login("emp@x.com"),
        json={"start_date": TUE.isoformat(), "end_date": TUE.isoformat()},
    )
    assert res.status_code == 422, res.text
    assert "biometric record" in res.json()["error"]["message"]


# ── the block, at approval time ────────────────────────────────────────────

def test_punches_arriving_after_filing_block_the_approval(
    client, login, db, team, mapped, punch
):
    """The connector syncs on its own schedule: a request filed before the day's
    punches arrive must still be caught when the PM comes to approve it."""
    created = _file(client, login, MON, MON)
    assert created.status_code == 201, created.text
    _full_day(punch, MON)

    res = client.post(
        f"{API}/{created.json()['id']}/approve", headers=login("mgr@x.com"), json={}
    )
    assert res.status_code == 422, res.text
    message = res.json()["error"]["message"]
    assert "this employee was present" in message
    assert "Reject the request" in message

    # And nothing moved: no Leave day was written and the request is still pending.
    req = db.query(LeaveRequest).filter_by(id=uuid.UUID(created.json()["id"])).one()
    assert req.status == LeaveStatus.pending


def test_approval_still_works_on_a_day_with_no_settled_punches(
    client, login, db, team, mapped, punch
):
    """The guard must not become a blanket refusal - a clean day still approves,
    and still marks the calendar."""
    db.add(
        EmployeeLeaveAdjustment(
            employee_id=team["employee"].id,
            effective_month=ledger.month_start(MON),
            days=Decimal("10.00"),
            reason="Opening balance",
        )
    )
    db.commit()
    created = _file(client, login, MON, MON, leave_type="casual")
    assert created.status_code == 201, created.text
    # One punch only: seen, but not settled - this must NOT block.
    punch(ist(MON, 9, 10))

    res = client.post(
        f"{API}/{created.json()['id']}/approve", headers=login("mgr@x.com"), json={}
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"


# ── one calculation, not two ───────────────────────────────────────────────

def test_the_guard_reads_the_same_verdict_the_calendar_shows(
    client, login, db, team, mapped, punch, auth_header
):
    """The guard and the employee's calendar must never disagree about whether a
    day is Present - that disagreement is the whole bug being fixed here."""
    _full_day(punch, MON)
    punch(ist(TUE, 9, 10))  # one punch: incomplete

    settled = settled_present_days(
        db, employee_id=team["employee"].id, date_from=MON, date_to=TUE
    )
    assert set(settled) == {MON}

    payload = client.get(
        "/api/v1/biometric/daily-summary",
        params={
            "from": MON.isoformat(),
            "to": TUE.isoformat(),
            "employee_id": str(team["employee"].id),
        },
        headers=login("mgr@x.com"),
    )
    assert payload.status_code == 200, payload.text
    by_date = {i["summary_date"]: i["classification"] for i in payload.json()["items"]}
    assert by_date[MON.isoformat()] == "present"
    assert by_date[TUE.isoformat()] == "incomplete"
    # The guard blocks exactly the days the calendar paints Present, no others.
    assert {d.isoformat() for d in settled} == {
        day for day, cls in by_date.items() if cls == "present"
    }
