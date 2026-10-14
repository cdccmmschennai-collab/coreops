"""Phase 2 - retrospective corrections and future-dated (planned) attendance.

    PAST date    any create/change must carry a reason (server-enforced)
    TODAY        unchanged - no reason required
    FUTURE date  every status allowed, STATUS ONLY - no check-in / check-out

Plus the audit detail every write now records (previous values, source,
retrospective), the Records read endpoints opening to future dates without
calling an empty future day a review problem, and two rules that must NOT move:

  * automatic reports are still produced only by the scheduled sweep, on its
    existing window - a future record creates nothing when it is saved;
  * a future Present / Half day still blocks a leave request for that day.

Dates are relative to today (the container runs on Asia/Kolkata, the same
calendar `attendance.service` judges past/future on).
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.audit.models import AuditLog
from app.modules.calendar.working_days import next_working_day
from app.modules.leave.models import LeaveRequest, LeaveStatus
from app.modules.users.models import UserRole
from app.modules.work_reports.auto_reports import generate_auto_leave_reports
from app.modules.work_reports.models import DailyWorkReport, DayStatus, ReportOrigin

ATTEND = "/api/v1/attendance"
REVIEW = "/api/v1/biometric/daily-review"
DETAIL = "/api/v1/biometric/daily-review/{employee_id}"

TODAY = date.today()
PAST = TODAY - timedelta(days=20)
FUTURE = TODAY + timedelta(days=20)

ALL_STATUSES = [s.value for s in AttendanceStatus]


@pytest.fixture()
def pm(auth_header):
    return auth_header("pm-phase2@x.com", role=UserRole.project_manager)


def _create(client, pm, employee_id, day: date, **over):
    body = {
        "employee_id": str(employee_id),
        "attendance_date": day.isoformat(),
        "status": "present",
    }
    body.update(over)
    return client.post(ATTEND, headers=pm, json=body)


def _audits(db, record_id):
    db.expire_all()
    return (
        db.execute(
            select(AuditLog)
            .where(AuditLog.entity_id == record_id)
            .order_by(AuditLog.created_at)
        )
        .scalars()
        .all()
    )


def _reason_error(res) -> bool:
    return res.status_code == 422 and "reason is required" in res.json()["error"]["message"]


# ---------------------------------------------------------------------------
# Retrospective creation and correction
# ---------------------------------------------------------------------------


def test_past_create_without_a_reason_is_refused(client, pm, make_employee, db):
    e = make_employee(employee_code="P2-1")
    res = _create(client, pm, e.id, PAST)
    assert _reason_error(res), res.text
    assert db.query(AttendanceRecord).count() == 0


def test_past_create_with_a_reason_is_saved(client, pm, make_employee):
    e = make_employee(employee_code="P2-2")
    res = _create(client, pm, e.id, PAST, status="absent", note="Did not attend.")
    assert res.status_code == 201, res.text
    assert res.json()["note"] == "Did not attend."


def test_whitespace_is_not_a_reason(client, pm, make_employee):
    e = make_employee(employee_code="P2-3")
    assert _reason_error(_create(client, pm, e.id, PAST, note="   "))


def test_past_correction_requires_a_reason_and_leaves_the_row_alone_without_one(
    client, pm, make_employee, make_attendance, db
):
    e = make_employee(employee_code="P2-4")
    rec = make_attendance(
        employee_id=e.id, attendance_date=PAST, status=AttendanceStatus.present
    )

    refused = client.patch(f"{ATTEND}/{rec.id}", headers=pm, json={"status": "leave"})
    assert _reason_error(refused), refused.text
    db.refresh(rec)
    assert rec.status == AttendanceStatus.present

    ok = client.patch(
        f"{ATTEND}/{rec.id}", headers=pm, json={"status": "leave", "note": "Was on leave."}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "leave"


def test_today_needs_no_reason(client, pm, make_employee):
    e = make_employee(employee_code="P2-5")
    assert _create(client, pm, e.id, TODAY).status_code == 201


def test_manual_leave_without_any_leave_request(client, pm, make_employee, db):
    """Recording Leave and requesting leave stay separate workflows: the PM's
    record creates no request."""
    e = make_employee(employee_code="P2-6")
    res = _create(client, pm, e.id, PAST, status="leave", note="Phoned in.")
    assert res.status_code == 201, res.text
    assert db.query(LeaveRequest).count() == 0


def test_legacy_bulk_requires_a_reason_for_a_past_date(client, pm, make_employee, db):
    e = make_employee(employee_code="P2-7")
    records = [{"employee_id": str(e.id), "status": "absent"}]

    refused = client.post(
        f"{ATTEND}/bulk", headers=pm, json={"date": PAST.isoformat(), "records": records}
    )
    assert _reason_error(refused), refused.text
    assert db.query(AttendanceRecord).count() == 0

    ok = client.post(
        f"{ATTEND}/bulk",
        headers=pm,
        json={"date": PAST.isoformat(), "records": records, "note": "Site closed."},
    )
    assert ok.status_code == 200, ok.text
    [row] = db.query(AttendanceRecord).all()
    assert row.note == "Site closed."


# ---------------------------------------------------------------------------
# Future dates: every status, status only
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ALL_STATUSES)
def test_every_status_can_be_planned_for_a_future_date(
    client, pm, make_employee, status
):
    e = make_employee(employee_code=f"F-{status}")
    res = _create(client, pm, e.id, FUTURE, status=status)
    assert res.status_code == 201, res.text
    assert res.json()["status"] == status
    assert res.json()["check_in_at"] is None
    assert res.json()["check_out_at"] is None


def test_future_create_with_times_is_refused(client, pm, make_employee, db):
    e = make_employee(employee_code="F-T1")
    res = _create(
        client, pm, e.id, FUTURE,
        check_in_at=f"{FUTURE.isoformat()}T09:00:00+05:30",
    )
    assert res.status_code == 422, res.text
    assert "future date" in res.json()["error"]["message"]
    assert db.query(AttendanceRecord).count() == 0


def test_future_update_cannot_add_times(client, pm, make_employee):
    e = make_employee(employee_code="F-T2")
    rec = _create(client, pm, e.id, FUTURE).json()
    res = client.patch(
        f"{ATTEND}/{rec['id']}",
        headers=pm,
        json={"check_out_at": f"{FUTURE.isoformat()}T18:00:00+05:30"},
    )
    assert res.status_code == 422, res.text
    # A status change on the same future day is still fine.
    ok = client.patch(f"{ATTEND}/{rec['id']}", headers=pm, json={"status": "leave"})
    assert ok.status_code == 200, ok.text


def test_legacy_bulk_refuses_times_on_a_future_date(client, pm, make_employee, db):
    e = make_employee(employee_code="F-T3")
    res = client.post(
        f"{ATTEND}/bulk",
        headers=pm,
        json={
            "date": FUTURE.isoformat(),
            "records": [{
                "employee_id": str(e.id),
                "status": "present",
                "check_in_at": f"{FUTURE.isoformat()}T09:00:00+05:30",
            }],
        },
    )
    assert res.status_code == 422, res.text
    assert db.query(AttendanceRecord).count() == 0


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_a_correction_audits_the_previous_values_and_how_it_was_made(
    client, pm, make_employee, db
):
    e = make_employee(employee_code="A-1")
    rec = _create(
        client, pm, e.id, PAST, status="half_day", note="Left at noon.",
        leave_day_fraction=0.5,
    ).json()
    res = client.patch(
        f"{ATTEND}/{rec['id']}",
        headers=pm,
        json={"status": "present", "note": "Came back after lunch."},
    )
    assert res.status_code == 200, res.text

    create_audit, update_audit = _audits(db, rec["id"])
    assert create_audit.details["source"] == "individual"
    assert create_audit.details["retrospective"] is True
    assert "previous_status" not in create_audit.details

    d = update_audit.details
    assert (d["previous_status"], d["status"]) == ("half_day", "present")
    assert d["previous_note"] == "Left at noon."
    assert d["note"] == "Came back after lunch."
    assert d["previous_leave_day_fraction"] == 0.5
    assert d["previous_check_in_at"] is None
    assert d["source"] == "individual"
    assert d["retrospective"] is True
    assert update_audit.actor_user_id is not None
    assert update_audit.created_at is not None


def test_a_future_record_is_not_retrospective(client, pm, make_employee, db):
    e = make_employee(employee_code="A-2")
    rec = _create(client, pm, e.id, FUTURE, status="leave").json()
    [audit] = _audits(db, rec["id"])
    assert audit.details["retrospective"] is False


def test_legacy_bulk_audits_each_row_as_bulk(client, pm, make_employee, db):
    e1 = make_employee(employee_code="A-3")
    e2 = make_employee(employee_code="A-4")
    client.post(
        f"{ATTEND}/bulk",
        headers=pm,
        json={
            "date": PAST.isoformat(),
            "records": [
                {"employee_id": str(e1.id), "status": "present"},
                {"employee_id": str(e2.id), "status": "absent"},
            ],
            "note": "Back-filled from the sign-in sheet.",
        },
    )
    rows = db.query(AttendanceRecord).all()
    assert len(rows) == 2
    for row in rows:
        [audit] = _audits(db, row.id)
        assert audit.details["source"] == "bulk"
        assert audit.details["note"] == "Back-filled from the sign-in sheet."


# ---------------------------------------------------------------------------
# Records read endpoints on a future date
# ---------------------------------------------------------------------------


def test_daily_review_opens_a_future_date_without_flagging_anyone(
    client, pm, make_employee
):
    e = make_employee(employee_code="R-1")
    res = client.get(REVIEW, params={"date": FUTURE.isoformat(), "limit": 100}, headers=pm)
    assert res.status_code == 200, res.text
    body = res.json()
    [row] = [r for r in body["items"] if r["employee_id"] == str(e.id)]
    # No punch on a day that has not happened is not a review problem...
    assert row["review_required"] is False
    assert row["blocking_reasons"] == []
    assert body["counts"]["review_required"] == 0
    # ...and no time can be entered for it.
    assert row["can_set_check_in"] is False
    assert row["can_set_check_out"] is False
    # Nothing is invented.
    assert row["first_in"] is None and row["last_out"] is None


def test_detail_opens_a_future_date_and_shows_the_planned_status(
    client, pm, make_employee
):
    e = make_employee(employee_code="R-2")
    _create(client, pm, e.id, FUTURE, status="comp_off")
    res = client.get(
        DETAIL.format(employee_id=e.id), params={"date": FUTURE.isoformat()}, headers=pm
    )
    assert res.status_code == 200, res.text
    row = res.json()["row"]
    assert row["attendance_status"] == "comp_off"
    assert row["review_required"] is False
    assert row["can_set_check_in"] is False
    assert res.json()["punches"] == []


def test_a_past_date_still_flags_a_missing_punch(client, pm, make_employee):
    """The future rule must not leak backwards: a past working day with no
    punch and no decision still needs review."""
    e = make_employee(employee_code="R-3")
    day = _past_weekday()
    res = client.get(REVIEW, params={"date": day.isoformat(), "limit": 100}, headers=pm)
    [row] = [r for r in res.json()["items"] if r["employee_id"] == str(e.id)]
    assert row["review_required"] is True
    assert row["can_set_check_in"] is True


def _past_weekday() -> date:
    """A weekday in the past - every weekday is a working day on the default
    calendar (only Saturdays and Sundays follow the weekly-off rule)."""
    day = PAST
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


# ---------------------------------------------------------------------------
# Automatic reports: unchanged schedule, nothing at save time
# ---------------------------------------------------------------------------


def _auto_reports(db, employee_id, day):
    db.expire_all()
    return (
        db.query(DailyWorkReport)
        .filter(
            DailyWorkReport.employee_id == employee_id,
            DailyWorkReport.report_date == day,
        )
        .all()
    )


def test_a_future_leave_record_produces_no_report_until_the_sweep_reaches_its_day(
    client, pm, make_employee, db
):
    e = make_employee(employee_code="S-1")
    day = next_working_day(db, TODAY + timedelta(days=10))

    assert _create(client, pm, e.id, day, status="leave").status_code == 201
    # Saving the record generates nothing.
    assert _auto_reports(db, e.id, day) == []

    # Today's scheduled run does not reach it: the window ends at today.
    generate_auto_leave_reports(db, today=TODAY)
    assert _auto_reports(db, e.id, day) == []

    # The run whose window includes the day files it, exactly once.
    generate_auto_leave_reports(db, today=day)
    generate_auto_leave_reports(db, today=day)
    [report] = _auto_reports(db, e.id, day)
    assert report.origin == ReportOrigin.auto
    assert report.day_status == DayStatus.leave


def test_consecutive_planned_leave_days_are_filed_one_run_at_a_time(
    client, pm, make_employee, db
):
    e = make_employee(employee_code="S-2")
    first = next_working_day(db, TODAY + timedelta(days=10))
    second = next_working_day(db, first)
    for day in (first, second):
        assert _create(client, pm, e.id, day, status="leave").status_code == 201

    generate_auto_leave_reports(db, today=first)
    assert len(_auto_reports(db, e.id, first)) == 1
    assert _auto_reports(db, e.id, second) == []

    generate_auto_leave_reports(db, today=second)
    assert len(_auto_reports(db, e.id, second)) == 1
    assert len(_auto_reports(db, e.id, first)) == 1


def test_changing_a_planned_leave_before_its_day_leaves_nothing_behind(
    client, pm, make_employee, db
):
    e = make_employee(employee_code="S-3")
    day = next_working_day(db, TODAY + timedelta(days=10))
    rec = _create(client, pm, e.id, day, status="leave").json()
    res = client.patch(f"{ATTEND}/{rec['id']}", headers=pm, json={"status": "present"})
    assert res.status_code == 200, res.text

    generate_auto_leave_reports(db, today=day)
    assert _auto_reports(db, e.id, day) == []


# ---------------------------------------------------------------------------
# A future Present / Half day still blocks leave for that day (decision B)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["present", "half_day"])
def test_future_worked_day_blocks_a_leave_request(
    client, pm, make_user, make_employee, login, status
):
    u = make_user(f"emp-b-{status}@x.com", role=UserRole.employee)
    e = make_employee(employee_code=f"B-{status}", user_id=u.id)
    day = TODAY + timedelta(days=14)
    assert _create(client, pm, e.id, day, status=status).status_code == 201

    res = client.post(
        "/api/v1/leave-requests",
        headers=login(f"emp-b-{status}@x.com"),
        json={"start_date": day.isoformat(), "end_date": day.isoformat(), "reason": "Trip"},
    )
    assert res.status_code == 422, res.text
    assert "marked present" in res.json()["error"]["message"]


def test_future_present_blocks_approving_an_existing_request(
    client, pm, make_user, make_employee, make_leave_request, login, db
):
    make_user("pm-b-appr@x.com", role=UserRole.project_manager)
    e = make_employee(employee_code="B-APPR")
    day = TODAY + timedelta(days=14)
    req = make_leave_request(employee_id=e.id, start_date=day, end_date=day)
    rec = _create(client, pm, e.id, day, status="present").json()

    res = client.post(
        f"/api/v1/leave-requests/{req.id}/approve",
        headers=login("pm-b-appr@x.com"),
        json={},
    )
    assert res.status_code == 422, res.text
    db.expire_all()
    # Nothing was bypassed: the request is still pending, the record untouched.
    assert db.get(LeaveRequest, req.id).status == LeaveStatus.pending
    assert db.get(AttendanceRecord, rec["id"]).status == AttendanceStatus.present
