"""Phase 11A - Permission history, detail and notifications.

Phase 11 pinned the RULES (allowance, guards, concurrency, audit) in
`test_permissions_phase11.py`; nothing here repeats them. What is new is the
USER-FACING surface: a monthly history that must not leak across months, a detail
response that must not invent consumed hours, and a notification flow that must
reach the other party and only the other party.

Dates are pinned to known weekdays, because a permission may only fall on a
working day.

    docker exec wms-backend-1 pytest tests/test_permissions_phase11a.py
"""
from datetime import date

import pytest

from app.modules.notifications.models import Notification
from app.modules.permissions.models import PermissionRequest, PermissionStatus
from app.modules.users.models import UserRole

API = "/api/v1/permission-requests"

# Maps the old `hours` shorthand these tests use onto a period - history/detail/
# notification wiring under test here doesn't care which half was picked.
_PERIOD_FOR_HOURS = {1: "first_half_1h", 2: "first_half_2h"}

# March 2027 (Mon 1st - Fri 5th) and the month either side of the 31 Mar / 1 Apr
# boundary, all working days.
MON = date(2027, 3, 1)
TUE = date(2027, 3, 2)
WED = date(2027, 3, 3)
MAR_30 = date(2027, 3, 30)
MAR_31 = date(2027, 3, 31)
APR_1 = date(2027, 4, 1)
APR_2 = date(2027, 4, 2)


@pytest.fixture()
def team(make_user, make_employee):
    mu = make_user("mgr@x.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MGR", user_id=mu.id, first_name="Meera",
                        last_name="Rao")
    m2 = make_user("mgr2@x.com", role=UserRole.project_manager)
    mgr2 = make_employee(employee_code="MGR2", user_id=m2.id, manager_id=mgr.id)
    eu = make_user("emp@x.com", role=UserRole.employee)
    # `reporting_pm_id`, not just `manager_id`: Phase 4B's routing fallback
    # (no report evidence here, so every submission below falls back) reads
    # `reporting_pm_id`, exactly as `leave/recipients.py` already does.
    emp = make_employee(employee_code="EMP011", user_id=eu.id, manager_id=mgr.id,
                        reporting_pm_id=mu.id, first_name="Arun", last_name="Kumar")
    ou = make_user("other@x.com", role=UserRole.employee)
    other = make_employee(employee_code="EMP012", user_id=ou.id, manager_id=mgr.id)
    return {
        "manager": mgr, "manager_user": mu,
        "manager2": mgr2,
        "employee": emp, "employee_user": eu,
        "other": other,
    }


def _submit(client, login, day: date, hours: int = 1, email="emp@x.com",
            reason="Appointment"):
    res = client.post(API, headers=login(email), json={
        "permission_date": day.isoformat(),
        "period": _PERIOD_FOR_HOURS[hours],
        "reason": reason,
    })
    assert res.status_code == 201, res.text
    return res.json()


def _approve(client, login, req_id, email="mgr@x.com", comment=None):
    return client.post(f"{API}/{req_id}/approve", headers=login(email),
                       json={"comment": comment})


def _history(client, login, email="emp@x.com", month: date | None = None,
             employee_id=None):
    sp = []
    if month:
        sp.append(f"month={month.isoformat()}")
    if employee_id:
        sp.append(f"employee_id={employee_id}")
    url = f"{API}/history" + (f"?{'&'.join(sp)}" if sp else "")
    res = client.get(url, headers=login(email))
    assert res.status_code == 200, res.text
    return res.json()


def _notifications(db, user_id):
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.created_at)
        .all()
    )


# ======================================================================
# Monthly history
# ======================================================================

def test_history_returns_only_the_selected_months_requests_and_balance(
    client, login, team
):
    """The table and the figure above it describe the SAME month, because both
    come from one set of server-computed bounds."""
    a = _submit(client, login, MON, 2)
    _approve(client, login, a["id"])
    _submit(client, login, TUE, 1)

    body = _history(client, login, month=MON)
    assert body["month"] == "2027-03-01"
    assert body["total"] == 2
    assert {i["permission_date"] for i in body["items"]} == {
        MON.isoformat(), TUE.isoformat(),
    }
    # 4h allowance, 2h approved, so 2h left - and the pending 1h has not touched it.
    assert (body["balance"]["allowance_hours"], body["balance"]["approved_hours"],
            body["balance"]["remaining_hours"]) == (4, 2, 2)


def test_history_is_newest_absence_first(client, login, team):
    """Ordered by the day off, not the day it was filed - the earliest date is
    submitted LAST here, so a created_at ordering would fail this."""
    _submit(client, login, MON, 1)
    _submit(client, login, WED, 1)
    _submit(client, login, TUE, 1)

    items = _history(client, login, month=MON)["items"]
    assert [i["permission_date"] for i in items] == [
        WED.isoformat(), TUE.isoformat(), MON.isoformat(),
    ]


def test_march_and_april_never_leak_into_each_other(client, login, team):
    """The month comes from permission_date, so 31 March and 1 April are separate
    histories AND separate allowances."""
    march = _submit(client, login, MAR_31, 2)
    _approve(client, login, march["id"])
    april = _submit(client, login, APR_1, 1)
    _approve(client, login, april["id"])

    m = _history(client, login, month=MAR_31)
    assert [i["permission_date"] for i in m["items"]] == [MAR_31.isoformat()]
    assert m["balance"]["remaining_hours"] == 2

    a = _history(client, login, month=APR_2)   # any date in April resolves to April
    assert a["month"] == "2027-04-01"
    assert [i["permission_date"] for i in a["items"]] == [APR_1.isoformat()]
    # April starts fresh at 4h; March's unused 2h did NOT carry forward.
    assert a["balance"]["remaining_hours"] == 3


def test_a_month_with_no_requests_is_empty_but_still_reports_the_allowance(
    client, login, team
):
    """The empty state must not be an error, and the month must still say 4h."""
    _submit(client, login, MON, 2)
    body = _history(client, login, month=APR_1)
    assert body["items"] == []
    assert body["total"] == 0
    assert (body["balance"]["approved_hours"], body["balance"]["remaining_hours"]) == (0, 4)


def test_history_defaults_to_the_current_business_month(client, login, team):
    """No `month` parameter = the current Chennai business month, which is what the
    KPI card's click lands on."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    body = _history(client, login)
    ist_today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    assert body["month"] == ist_today.replace(day=1).isoformat()


def test_a_project_manager_sees_their_own_history_and_may_read_an_employees(
    client, login, team
):
    """A PM is an employee and takes permission too, so their own history must
    work - and they may look at a team member's."""
    own = _submit(client, login, MON, 1, email="mgr@x.com")
    _approve(client, login, own["id"], email="mgr2@x.com")
    theirs = _submit(client, login, TUE, 2)

    mine = _history(client, login, email="mgr@x.com", month=MON)
    assert [i["id"] for i in mine["items"]] == [own["id"]]
    assert mine["balance"]["remaining_hours"] == 3

    looked_up = _history(client, login, email="mgr@x.com", month=MON,
                         employee_id=team["employee"].id)
    assert [i["id"] for i in looked_up["items"]] == [theirs["id"]]
    assert looked_up["employee_id"] == str(team["employee"].id)


def test_an_employee_cannot_read_another_employees_history(client, login, team):
    res = client.get(
        f"{API}/history?employee_id={team['other'].id}", headers=login("emp@x.com")
    )
    assert res.status_code == 403, res.text
    # Naming themselves explicitly is fine.
    ok = client.get(
        f"{API}/history?employee_id={team['employee'].id}", headers=login("emp@x.com")
    )
    assert ok.status_code == 200, ok.text


# ======================================================================
# Detail
# ======================================================================

def test_detail_carries_names_and_the_approved_balance_movement(
    client, login, team
):
    """The "Before approval / Permission taken / Remaining" figures, all derived
    server-side so the page does no arithmetic."""
    req = _submit(client, login, MON, 2)
    _approve(client, login, req["id"], comment="Fine, cover the afternoon")

    res = client.get(f"{API}/{req['id']}", headers=login("emp@x.com"))
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["employee_name"] == "Arun Kumar"
    assert body["employee_code"] == "EMP011"
    assert body["reviewer_name"] == "Meera Rao"
    assert body["reviewed_at"] is not None
    assert body["manager_comment"] == "Fine, cover the afternoon"

    b = body["balance"]
    assert b["month"] == "2027-03-01"
    assert b["allowance_hours"] == 4
    assert b["remaining_before_request"] == 4
    assert b["consumed_by_request"] == 2
    assert b["remaining_hours"] == 2
    # A decided request has no forecast left to show.
    assert b["remaining_if_approved"] is None


def test_a_pending_detail_forecasts_without_consuming(client, login, team):
    req = _submit(client, login, MON, 2)
    b = client.get(f"{API}/{req['id']}", headers=login("emp@x.com")).json()["balance"]

    assert b["consumed_by_request"] == 0
    assert b["approved_hours"] == 0
    assert b["remaining_hours"] == 4
    assert b["remaining_if_approved"] == 2
    # Nothing was spent, so "before" is just the current figure.
    assert b["remaining_before_request"] == 4


def test_rejected_and_cancelled_details_report_zero_consumed(client, login, team):
    """Neither may read as if its hours were still spent - a cancelled request in
    particular has given them back."""
    rejected = _submit(client, login, MON, 2)
    client.post(f"{API}/{rejected['id']}/reject", headers=login("mgr@x.com"),
                json={"comment": "Delivery day"})

    cancelled = _submit(client, login, TUE, 2)
    _approve(client, login, cancelled["id"])
    # Withdrawn outright by the PM. Since Phase 4E the employee's own route out
    # of an APPROVED permission is a cancellation request a reviewer decides;
    # either way the settled row must read as having consumed nothing.
    client.post(f"{API}/{cancelled['id']}/cancel", headers=login("mgr@x.com"))

    for req_id in (rejected["id"], cancelled["id"]):
        b = client.get(f"{API}/{req_id}", headers=login("emp@x.com")).json()["balance"]
        assert b["consumed_by_request"] == 0, req_id
        assert b["remaining_if_approved"] is None, req_id
        # Both were the only requests in the month, so nothing is approved in it.
        assert b["approved_hours"] == 0, req_id
        assert b["remaining_hours"] == 4, req_id
        assert b["remaining_before_request"] == 4, req_id


def test_detail_authorization_matches_the_list(client, login, team):
    """Employee: own only. Project manager: any. The detail endpoint must not be a
    way around the list's scoping."""
    mine = _submit(client, login, MON, 1)
    theirs = _submit(client, login, TUE, 1, email="other@x.com")

    h = login("emp@x.com")
    assert client.get(f"{API}/{mine['id']}", headers=h).status_code == 200
    assert client.get(f"{API}/{theirs['id']}", headers=h).status_code == 403

    m = login("mgr@x.com")
    for req_id in (mine["id"], theirs["id"]):
        assert client.get(f"{API}/{req_id}", headers=m).status_code == 200, req_id


def test_a_pending_detail_has_no_reviewer_yet(client, login, team):
    req = _submit(client, login, MON, 1)
    body = client.get(f"{API}/{req['id']}", headers=login("emp@x.com")).json()
    assert (body["reviewer_name"], body["reviewed_at"], body["manager_comment"]) == (
        None, None, None,
    )


# ======================================================================
# Notifications
# ======================================================================

def test_submitting_notifies_the_manager_and_not_the_author(client, login, team, db):
    req = _submit(client, login, MON, 2)

    db.expire_all()
    mgr_notes = _notifications(db, team["manager_user"].id)
    assert [n.type for n in mgr_notes] == ["permission_submitted"]
    note = mgr_notes[0]
    assert "Arun Kumar" in note.message
    assert "01 Mar 2027" in note.message
    assert "1st Half - 2 Hours" in note.message
    assert note.target_url == f"/attendance/permission/{req['id']}"
    assert note.entity_type == "permission_request"

    # The employee who filed it is told nothing about their own action.
    assert _notifications(db, team["employee_user"].id) == []


def test_approval_notifies_the_employee_with_date_duration_and_status(
    client, login, team, db
):
    """The wording the phase specifies, and the remaining balance with it."""
    req = _submit(client, login, MON, 2)
    _approve(client, login, req["id"])

    db.expire_all()
    notes = _notifications(db, team["employee_user"].id)
    assert [n.type for n in notes] == ["permission_approved"]
    msg = notes[0].message
    assert "Your permission request for 01 Mar 2027 for 1st Half - 2 Hours has been approved." in msg
    assert "2h of permission remaining" in msg
    assert notes[0].target_url == f"/attendance/permission/{req['id']}"

    # The deciding manager is not notified of their own decision; they only ever
    # got the original submission.
    assert [n.type for n in _notifications(db, team["manager_user"].id)] == [
        "permission_submitted"
    ]


def test_rejection_notifies_the_employee_and_includes_the_manager_note(
    client, login, team, db
):
    req = _submit(client, login, MON, 2)
    client.post(f"{API}/{req['id']}/reject", headers=login("mgr@x.com"),
                json={"comment": "Delivery day - please reschedule"})

    db.expire_all()
    notes = _notifications(db, team["employee_user"].id)
    assert [n.type for n in notes] == ["permission_rejected"]
    msg = notes[0].message
    assert "Your permission request for 01 Mar 2027 for 1st Half - 2 Hours has been rejected." in msg
    assert "Note: Delivery day - please reschedule" in msg


def test_a_rejection_without_a_note_says_nothing_about_one(client, login, team, db):
    req = _submit(client, login, MON, 1)
    client.post(f"{API}/{req['id']}/reject", headers=login("mgr@x.com"), json={})

    db.expire_all()
    msg = _notifications(db, team["employee_user"].id)[0].message
    assert "Note:" not in msg


def test_an_employee_cancelling_notifies_their_manager_not_themselves(
    client, login, team, db
):
    """A PENDING request - the only one an employee still withdraws in one step
    since Phase 4E. The manager owns the queue it has just left, so they are the
    one told, and no hours are quoted because a pending request never held any.
    """
    req = _submit(client, login, MON, 2)
    # Clear the submission notification so the cancellation is unambiguous.
    db.query(Notification).delete()
    db.commit()

    assert client.post(f"{API}/{req['id']}/cancel",
                       headers=login("emp@x.com")).status_code == 200

    db.expire_all()
    assert _notifications(db, team["employee_user"].id) == []
    mgr_notes = _notifications(db, team["manager_user"].id)
    assert [n.type for n in mgr_notes] == ["permission_cancelled"]
    assert "Arun Kumar" in mgr_notes[0].message
    assert "of permission remaining" not in mgr_notes[0].message


def test_a_manager_cancelling_notifies_the_employee(client, login, team, db):
    req = _submit(client, login, MON, 2)
    _approve(client, login, req["id"])
    db.query(Notification).delete()
    db.commit()

    assert client.post(f"{API}/{req['id']}/cancel",
                       headers=login("mgr@x.com")).status_code == 200

    db.expire_all()
    notes = _notifications(db, team["employee_user"].id)
    assert [n.type for n in notes] == ["permission_cancelled"]
    assert "01 Mar 2027" in notes[0].message
    assert "4h of permission remaining" in notes[0].message


def test_a_manager_cancelling_their_own_permission_is_not_told_by_themselves(
    client, login, team, db
):
    """Routing: a project manager cancelling their OWN approved permission takes
    the author branch, so their own manager hears about it and they do not."""
    own = _submit(client, login, MON, 2, email="mgr2@x.com")
    _approve(client, login, own["id"], email="mgr@x.com")
    db.query(Notification).delete()
    db.commit()

    assert client.post(f"{API}/{own['id']}/cancel",
                       headers=login("mgr2@x.com")).status_code == 200

    db.expire_all()
    # mgr2's manager is mgr, a different person, so mgr is the one told.
    assert [n.type for n in _notifications(db, team["manager_user"].id)] == [
        "permission_cancelled"
    ]


def test_the_self_notification_backstop_drops_a_push_aimed_at_the_actor(
    team, db
):
    """The `_push` guard, exercised directly - because nothing in the app can
    currently reach it.

    Every route already crosses parties: self-review is refused, a cancellation
    goes to whichever side did not perform it, and `employees_no_self_manager`
    stops an employee being their own manager. So this is a backstop for those
    three decisions changing, and the only honest way to test a backstop is to
    aim at it deliberately rather than to fabricate a DB state the schema forbids.
    """
    from app.modules.permissions.service import _push

    actor = team["employee_user"]
    _push(db, actor=actor, user_id=actor.id, type_="permission_approved",
          title="Should not be delivered", message="...")
    db.commit()

    db.expire_all()
    assert _notifications(db, actor.id) == []

    # ...and it is the identity check doing it, not a broken push: the same call
    # aimed at somebody else delivers.
    other_user_id = team["manager_user"].id
    _push(db, actor=actor, user_id=other_user_id, type_="permission_approved",
          title="Delivered", message="...")
    db.commit()

    db.expire_all()
    assert [n.title for n in _notifications(db, other_user_id)] == ["Delivered"]


def test_a_failed_decision_notifies_nobody(client, login, team, db):
    """A refused approval must not tell the employee anything happened."""
    spent = _submit(client, login, MON, 2)
    _approve(client, login, spent["id"])
    spent2 = _submit(client, login, TUE, 2)
    _approve(client, login, spent2["id"])
    db.query(Notification).delete()
    db.commit()

    starved = _submit(client, login, WED, 1)
    db.query(Notification).delete()   # drop the submission notification
    db.commit()
    assert _approve(client, login, starved["id"]).status_code == 422

    db.expire_all()
    assert _notifications(db, team["employee_user"].id) == []


# ======================================================================
# The Phase 11 rules still hold
# ======================================================================

def test_the_allowance_rule_is_unchanged_by_this_phase(client, login, team, db):
    """A guard against 11A having quietly altered the derivation while adding
    surfaces on top of it: 4h -> 3h -> 1h, pending free, cancellation restoring."""
    first = _submit(client, login, MON, 1)
    _approve(client, login, first["id"])
    second = _submit(client, login, TUE, 2)
    _approve(client, login, second["id"])
    pending = _submit(client, login, WED, 1)

    assert _history(client, login, month=MON)["balance"]["remaining_hours"] == 1
    client.post(f"{API}/{second['id']}/cancel", headers=login("mgr@x.com"))
    assert _history(client, login, month=MON)["balance"]["remaining_hours"] == 3

    db.expire_all()
    assert db.get(PermissionRequest, pending["id"]).status == PermissionStatus.pending
