"""PM-manual Permission - recorded from the Daily Attendance Review edit dialog.

The PM's selector rides on the ordinary attendance write (`permission_period` on
POST/PATCH /attendance) and lands in the SAME `permission_requests` ledger an
approved request does - but as `recorded`, never `approved`, and never as a
request (nothing pending, routed, queued or in All Requests). These pin that the
two paths share one allowance, one history and one notification channel, that
the two origins stay distinguishable, and that the manual path never touches the
attendance status, leave or work reports.

Dates are pinned to known March 2027 weekdays (as in test_permissions_phase11),
so the month is open for employee requests too.

    docker exec wms-backend-1 pytest tests/test_permission_manual.py
"""
from datetime import date

import pytest

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.audit.models import AuditLog
from app.modules.leave.models import LeaveRequest
from app.modules.leave_balances.ledger import leave_days_for
from app.modules.notifications.models import Notification
from app.modules.permissions.models import (
    PERIOD_LABELS,
    PermissionPeriod,
    PermissionRequest,
    PermissionStatus,
)
from app.modules.users.models import UserRole
from app.modules.work_reports.auto_reports import (
    generate_auto_leave_reports,
    generate_auto_reports,
)
from app.modules.work_reports.models import DailyWorkReport

API = "/api/v1/permission-requests"
ATTEND = "/api/v1/attendance"

MON = date(2027, 3, 1)
TUE = date(2027, 3, 2)
WED = date(2027, 3, 3)
THU = date(2027, 3, 4)
FRI = date(2027, 3, 5)
NEXT_MON = date(2027, 3, 8)
SAT = date(2027, 3, 13)  # 2nd Saturday - non-working
APR_1 = date(2027, 4, 1)


@pytest.fixture()
def team(make_user, make_employee):
    mu = make_user("mgr@x.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MGR", user_id=mu.id)
    eu = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(
        employee_code="EMP011", user_id=eu.id, manager_id=mgr.id,
        first_name="Asha", last_name="R",
    )
    return {"manager": mgr, "manager_user": mu, "employee": emp, "employee_user": eu}


def _remaining(client, login, month: date = MON) -> int:
    res = client.get(f"{API}/balance/me?month={month.isoformat()}", headers=login("emp@x.com"))
    assert res.status_code == 200, res.text
    return res.json()["remaining_hours"]


def _record(client, login, team, day: date, period: str | None, *, status="present"):
    """The dialog's save for a day with no attendance record yet."""
    return client.post(ATTEND, headers=login("mgr@x.com"), json={
        "employee_id": str(team["employee"].id),
        "attendance_date": day.isoformat(),
        "status": status,
        "permission_period": period,
    })


def _patch(client, login, record_id, body: dict):
    return client.patch(f"{ATTEND}/{record_id}", headers=login("mgr@x.com"), json=body)


def _request_and_approve(client, login, day: date, period="first_half_1h"):
    res = client.post(API, headers=login("emp@x.com"), json={
        "permission_date": day.isoformat(), "period": period,
    })
    assert res.status_code == 201, res.text
    ok = client.post(f"{API}/{res.json()['id']}/approve", headers=login("mgr@x.com"), json={})
    assert ok.status_code == 200, ok.text
    return ok.json()


def _live(db, employee_id, day: date) -> list[PermissionRequest]:
    """The day's consuming permission, whichever path wrote it."""
    db.expire_all()
    return db.query(PermissionRequest).filter(
        PermissionRequest.employee_id == employee_id,
        PermissionRequest.permission_date == day,
        PermissionRequest.status.in_(
            (PermissionStatus.approved, PermissionStatus.recorded)
        ),
    ).all()


def _notifications(db, user_id, type_=None) -> list[Notification]:
    db.expire_all()
    q = db.query(Notification).filter(Notification.user_id == user_id)
    if type_:
        q = q.filter(Notification.type == type_)
    return q.all()


# ======================================================================
# Recording
# ======================================================================

def test_pm_records_a_permission_and_it_lands_in_the_ledger(client, login, team, db):
    res = _record(client, login, team, MON, "first_half_1h")
    assert res.status_code == 201, res.text
    # The day stays exactly what the PM set: Present, not a "permission" status.
    assert res.json()["status"] == "present"

    [row] = _live(db, team["employee"].id, MON)
    # Recorded - never Approved: nobody requested it and nobody reviewed it.
    assert row.status == PermissionStatus.recorded
    assert row.period == PermissionPeriod.first_half_1h
    assert row.duration_hours == 1
    assert row.manager_id == team["manager"].id  # "Recorded by"
    assert row.reviewed_at is None
    assert row.routed_project_id is None
    assert row.created_by == team["manager_user"].id
    assert _remaining(client, login) == 3

    # Audited through the permission trail as a recording, not an approval.
    audit = db.query(AuditLog).filter(
        AuditLog.entity_id == row.id, AuditLog.action == "permission.record"
    ).one()
    assert audit.details["source"] == "attendance_review"
    assert audit.details["status"] == "recorded"
    assert audit.details["remaining_after"] == 3
    assert db.query(AuditLog).filter(
        AuditLog.entity_id == row.id,
        AuditLog.action.in_(("permission.request.submit", "permission.request.approve")),
    ).count() == 0


def test_recording_creates_no_permission_request(client, login, team, db):
    """No request lifecycle at all: nothing pending, nothing routed, nobody asked
    to review it, and it is absent from the requests views."""
    assert _record(client, login, team, MON, "first_half_1h").status_code == 201
    db.expire_all()
    [row] = db.query(PermissionRequest).all()
    assert row.status == PermissionStatus.recorded

    # No submission notification to any reviewer.
    assert _notifications(db, team["manager_user"].id, "permission_submitted") == []
    # Not in the pending review queue.
    queue = client.get(f"{API}?status=pending", headers=login("mgr@x.com")).json()
    assert queue["total"] == 0
    # Not in All Requests, for the PM or the employee.
    for who in ("mgr@x.com", "emp@x.com"):
        res = client.get("/api/v1/all-requests", headers=login(who))
        assert res.status_code == 200, res.text
        assert res.json()["total"] == 0, who


def test_the_employee_is_notified_of_the_recording(client, login, team, db):
    assert _record(client, login, team, MON, "second_half_2h").status_code == 201
    [note] = _notifications(db, team["employee_user"].id, "permission_approved")
    assert note.title == "Permission recorded"
    assert "recorded 2nd Half - 2 Hours of permission for you" in note.message
    assert "approved" not in (note.title + note.message).lower()
    assert "01 Mar 2027" in note.message
    assert "2h of permission remaining for March 2027" in note.message
    assert note.entity_type == "permission_request"
    assert note.target_url.startswith("/attendance/permission/")


def test_no_work_report_and_no_leave_follow_from_a_permission(client, login, team, db):
    rec = _record(client, login, team, MON, "first_half_1h")
    assert rec.status_code == 201, rec.text

    # Including the 01:00 job's two sweeps run over that very day.
    generate_auto_reports(db, dates=[MON])
    generate_auto_leave_reports(db, dates=[MON])

    db.expire_all()
    assert db.query(DailyWorkReport).filter(
        DailyWorkReport.employee_id == team["employee"].id
    ).count() == 0
    assert db.query(LeaveRequest).filter(
        LeaveRequest.employee_id == team["employee"].id
    ).count() == 0
    record = db.get(AttendanceRecord, rec.json()["id"])
    assert record.status == AttendanceStatus.present
    assert record.leave_day_fraction is None
    assert leave_days_for(record.status, record.leave_day_fraction) == 0


def test_omitting_the_field_records_no_permission(client, login, team, db):
    """The selector's default, "No Permission", sends nothing - and an explicit
    null on a day with none is equally a no-op."""
    res = client.post(ATTEND, headers=login("mgr@x.com"), json={
        "employee_id": str(team["employee"].id),
        "attendance_date": MON.isoformat(),
        "status": "present",
    })
    assert res.status_code == 201, res.text
    assert _patch(client, login, res.json()["id"], {"permission_period": None}).status_code == 200
    db.expire_all()
    assert db.query(PermissionRequest).count() == 0
    assert _remaining(client, login) == 4
    assert _notifications(db, team["employee_user"].id) == []


def test_the_options_are_exactly_the_request_flows_four(client, login, team):
    """One enum for both paths: the four request options are accepted and
    nothing else is."""
    assert set(PERIOD_LABELS) == set(PermissionPeriod)
    for day, period in zip((MON, TUE), ("first_half_1h", "second_half_1h")):
        assert _record(client, login, team, day, period).status_code == 201
    for bad in ("1h", "third_half", "FIRST_HALF_1H", ""):
        assert _record(client, login, team, WED, bad).status_code == 422, bad


# ======================================================================
# One allowance for both paths
# ======================================================================

def test_both_paths_share_the_monthly_allowance_and_the_fifth_is_refused(
    client, login, team, db
):
    _request_and_approve(client, login, MON)                              # 1st
    assert _record(client, login, team, TUE, "first_half_1h").status_code == 201   # 2nd
    _request_and_approve(client, login, WED)                              # 3rd
    assert _record(client, login, team, THU, "second_half_1h").status_code == 201  # 4th
    assert _remaining(client, login) == 0

    # 5th - the PM cannot record it...
    pm5 = _record(client, login, team, FRI, "first_half_1h")
    assert pm5.status_code == 422, pm5.text
    assert "Insufficient permission balance" in pm5.json()["error"]["message"]
    # ...and the refusal rolled the whole save back, attendance row included.
    db.expire_all()
    assert db.query(AttendanceRecord).filter_by(attendance_date=FRI).count() == 0

    # ...and the employee cannot request it.
    emp5 = client.post(API, headers=login("emp@x.com"), json={
        "permission_date": FRI.isoformat(), "period": "first_half_1h",
    })
    assert emp5.status_code == 422, emp5.text
    assert "Insufficient permission balance" in emp5.json()["error"]["message"]
    assert _remaining(client, login) == 0


def test_next_month_is_available_again_on_both_paths(client, login, team):
    for day in (MON, TUE):
        assert _record(client, login, team, day, "first_half_2h").status_code == 201
    assert _remaining(client, login) == 0

    assert _remaining(client, login, month=APR_1) == 4
    assert _record(client, login, team, APR_1, "first_half_1h").status_code == 201
    res = client.post(API, headers=login("emp@x.com"), json={
        "permission_date": date(2027, 4, 2).isoformat(), "period": "first_half_1h",
    })
    assert res.status_code == 201, res.text
    assert _remaining(client, login, month=APR_1) == 3


# ======================================================================
# Reconciliation: re-save, change, remove
# ======================================================================

def test_saving_the_same_permission_again_does_not_double_consume(client, login, team, db):
    rec = _record(client, login, team, MON, "first_half_1h").json()
    for _ in range(2):
        res = _patch(client, login, rec["id"], {"status": "present", "permission_period": "first_half_1h"})
        assert res.status_code == 200, res.text
    assert len(_live(db, team["employee"].id, MON)) == 1
    assert db.query(PermissionRequest).count() == 1
    assert _remaining(client, login) == 3
    assert len(_notifications(db, team["employee_user"].id, "permission_approved")) == 1


def test_permission_to_no_permission_restores_the_hours(client, login, team, db):
    rec = _record(client, login, team, MON, "first_half_2h").json()
    assert _remaining(client, login) == 2

    res = _patch(client, login, rec["id"], {"permission_period": None})
    assert res.status_code == 200, res.text
    assert _live(db, team["employee"].id, MON) == []
    assert db.query(PermissionRequest).one().status == PermissionStatus.cancelled
    assert _remaining(client, login) == 4
    [note] = _notifications(db, team["employee_user"].id, "permission_cancelled")
    assert "1st Half - 2 Hours" in note.message
    assert "4h of permission remaining" in note.message


def test_permission_to_another_permission_reconciles(client, login, team, db):
    rec = _record(client, login, team, MON, "first_half_1h").json()
    res = _patch(client, login, rec["id"], {"permission_period": "second_half_2h"})
    assert res.status_code == 200, res.text

    [live] = _live(db, team["employee"].id, MON)
    assert live.period == PermissionPeriod.second_half_2h
    statuses = sorted(r.status.value for r in db.query(PermissionRequest).all())
    assert statuses == ["cancelled", "recorded"]
    assert _remaining(client, login) == 2
    updated = [
        n for n in _notifications(db, team["employee_user"].id, "permission_approved")
        if n.title == "Your permission was updated"
    ]
    assert len(updated) == 1
    assert "from 1st Half - 1 Hour to 2nd Half - 2 Hours" in updated[0].message


def test_a_swap_the_month_cannot_cover_changes_nothing(client, login, team, db):
    _request_and_approve(client, login, MON, "first_half_2h")
    rec = _record(client, login, team, TUE, "first_half_1h").json()
    _request_and_approve(client, login, WED)
    assert _remaining(client, login) == 0

    # 1h -> 2h frees 1h but needs 2h: refused, and the whole save rolls back.
    res = _patch(client, login, rec["id"], {"status": "half_day", "permission_period": "first_half_2h"})
    assert res.status_code == 422, res.text
    [live] = _live(db, team["employee"].id, TUE)
    assert live.period == PermissionPeriod.first_half_1h
    assert db.get(AttendanceRecord, rec["id"]).status == AttendanceStatus.present
    assert _remaining(client, login) == 0


def test_changing_the_status_leaves_the_permission_alone(client, login, team, db):
    rec = _record(client, login, team, MON, "first_half_1h").json()
    res = _patch(client, login, rec["id"], {"status": "half_day", "leave_day_fraction": 0})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "half_day"
    [live] = _live(db, team["employee"].id, MON)
    assert live.period == PermissionPeriod.first_half_1h
    assert _remaining(client, login) == 3


# ======================================================================
# Guards
# ======================================================================

def test_a_pending_request_on_the_day_is_left_to_the_review_queue(
    client, login, team, db, make_attendance
):
    pending = client.post(API, headers=login("emp@x.com"), json={
        "permission_date": MON.isoformat(), "period": "first_half_1h",
    }).json()
    rec = make_attendance(employee_id=team["employee"].id, attendance_date=MON)

    res = _patch(client, login, rec.id, {"permission_period": "first_half_2h"})
    assert res.status_code == 409, res.text
    assert "pending permission request" in res.json()["error"]["message"]
    db.expire_all()
    assert db.get(PermissionRequest, pending["id"]).status == PermissionStatus.pending
    # The default "No Permission" save does not touch the pending request either.
    assert _patch(client, login, rec.id, {"status": "present"}).status_code == 200
    assert db.get(PermissionRequest, pending["id"]).status == PermissionStatus.pending


def test_a_pm_cannot_record_a_permission_for_themselves(client, login, team, db):
    res = client.post(ATTEND, headers=login("mgr@x.com"), json={
        "employee_id": str(team["manager"].id),
        "attendance_date": MON.isoformat(),
        "status": "present",
        "permission_period": "first_half_1h",
    })
    assert res.status_code == 403, res.text
    db.expire_all()
    assert db.query(PermissionRequest).count() == 0


def test_a_non_working_day_cannot_have_a_permission(client, login, team):
    res = _record(client, login, team, SAT, "first_half_1h", status="weekend")
    assert res.status_code == 422, res.text
    assert "not a working day" in res.json()["error"]["message"]


def test_an_employee_cannot_record_through_attendance(client, login, team):
    res = client.post(ATTEND, headers=login("emp@x.com"), json={
        "employee_id": str(team["employee"].id),
        "attendance_date": MON.isoformat(),
        "status": "present",
        "permission_period": "first_half_1h",
    })
    assert res.status_code == 403


def test_the_daily_review_row_carries_the_recorded_option(client, login, team):
    """What the edit dialog seeds its selector from. A PAST day (10 Aug 2026, a
    Monday in a closed month): `/daily-review` refuses future dates, and a PM may
    still settle a closed month's record, as a reviewer may approve in one."""
    day = date(2026, 8, 10)
    rec = _record(client, login, team, day, "second_half_1h")
    assert rec.status_code == 201, rec.text

    res = client.get(
        "/api/v1/biometric/daily-review",
        params={"date": day.isoformat(), "limit": 100},
        headers=login("mgr@x.com"),
    )
    assert res.status_code == 200, res.text
    [row] = [r for r in res.json()["items"] if r["employee_id"] == str(team["employee"].id)]
    assert row["attendance_status"] == "present"
    assert (row["permission_hours"], row["permission_period"]) == (1, "second_half_1h")


# ======================================================================
# Ledger / history
# ======================================================================

def test_history_lists_requested_and_recorded_permissions_alike(client, login, team):
    _request_and_approve(client, login, MON)
    assert _record(client, login, team, TUE, "second_half_1h").status_code == 201

    res = client.get(f"{API}/history?month={MON.isoformat()}", headers=login("emp@x.com"))
    assert res.status_code == 200, res.text
    body = res.json()
    by_date = {row["permission_date"]: row for row in body["items"]}
    assert by_date[MON.isoformat()]["status"] == "approved"
    assert by_date[MON.isoformat()]["recorded_by_manager"] is False
    assert by_date[TUE.isoformat()]["status"] == "recorded"
    assert by_date[TUE.isoformat()]["recorded_by_manager"] is True
    assert body["balance"]["remaining_hours"] == 2

    detail = client.get(f"{API}/{by_date[TUE.isoformat()]['id']}", headers=login("emp@x.com"))
    assert detail.status_code == 200, detail.text
    d = detail.json()
    assert d["status"] == "recorded"
    assert d["recorded_by_manager"] is True
    assert d["reviewer_name"] == team["manager"].full_name  # "Recorded by"
    assert d["reviewed_at"] is None
    assert d["routed_to_name"] is None
    assert d["balance"]["consumed_by_request"] == 1

    # The employee-requested one is untouched: Approved, with its reviewer.
    approved = client.get(f"{API}/{by_date[MON.isoformat()]['id']}", headers=login("emp@x.com")).json()
    assert approved["status"] == "approved"
    assert approved["recorded_by_manager"] is False
    assert approved["reviewed_at"] is not None


# ======================================================================
# Cancellation of a recorded permission
# ======================================================================

def test_pm_cancels_a_recorded_permission_and_it_keeps_its_origin(client, login, team, db):
    _record(client, login, team, MON, "first_half_2h")
    [row] = _live(db, team["employee"].id, MON)
    assert _remaining(client, login) == 2

    res = client.post(f"{API}/{row.id}/cancel", headers=login("mgr@x.com"))
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "cancelled"
    assert _remaining(client, login) == 4

    # Still identifiably manager-recorded - never turned into an approved request.
    detail = client.get(f"{API}/{row.id}", headers=login("emp@x.com")).json()
    assert detail["status"] == "cancelled"
    assert detail["recorded_by_manager"] is True
    assert detail["reviewed_at"] is None
    assert detail["balance"]["consumed_by_request"] == 0

    [note] = _notifications(db, team["employee_user"].id, "permission_cancelled")
    assert note.title == "Your permission was cancelled"
    assert "permission request" not in note.message
    assert "4h of permission remaining" in note.message

    # Cancelling twice cannot restore twice.
    again = client.post(f"{API}/{row.id}/cancel", headers=login("mgr@x.com"))
    assert again.status_code == 409
    assert _remaining(client, login) == 4


def test_the_employee_cannot_withdraw_a_recorded_permission(client, login, team, db):
    """It was the manager's record, so the manager removes it - neither the
    one-step cancel nor a cancellation request is open to the employee."""
    _record(client, login, team, MON, "first_half_1h")
    [row] = _live(db, team["employee"].id, MON)

    for path in ("cancel", "request-cancellation"):
        res = client.post(f"{API}/{row.id}/{path}", headers=login("emp@x.com"))
        assert res.status_code == 409, (path, res.text)
        assert "recorded by your manager" in res.json()["error"]["message"]
    db.expire_all()
    assert db.get(PermissionRequest, row.id).status == PermissionStatus.recorded
    assert _remaining(client, login) == 3
