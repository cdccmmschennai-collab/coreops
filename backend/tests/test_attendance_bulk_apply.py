"""Phase 4 - POST /attendance/bulk-apply: one status over employees x dates.

    dry_run=true    preview: per-pair outcomes, nothing written
    dry_run=false   apply: partial success, the same outcomes, written

Outcomes: created / updated / unchanged / protected / rejected (with a reason).
Status only - times and permission data are never written. One summary
notification per employee per action; one audit entry per changed pair.
Automatic reports stay with the scheduled sweep.

Dates are relative to today (the container runs on Asia/Kolkata, the calendar
`attendance.service` judges past/future on).
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.modules.attendance import bulk_apply as bulk_module
from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.audit.models import AuditLog
from app.modules.calendar.working_days import next_working_day
from app.modules.employees.models import EmployeeStatus
from app.modules.leave.effects import apply_leave_approved, reverse_leave_approved
from app.modules.leave.models import LeaveStatus
from app.modules.notifications.models import Notification
from app.modules.permissions.models import PermissionRequest, PermissionStatus
from app.modules.users.models import User, UserRole
from app.modules.work_reports.auto_reports import generate_auto_leave_reports
from app.modules.work_reports.models import DailyWorkReport, DayStatus, ReportOrigin

URL = "/api/v1/attendance/bulk-apply"

TODAY = date.today()
ALL_STATUSES = [s.value for s in AttendanceStatus]


@pytest.fixture()
def pm(auth_header):
    return auth_header("pm-bulk@x.com", role=UserRole.project_manager)


def _working(db, n: int) -> date:
    """Distinct future working days: n=10 is the first working day after
    today+9, n=11 the next one, and so on."""
    day = TODAY + timedelta(days=9)
    for _ in range(n - 9):
        day = next_working_day(db, day)
    return day


def _past_working(db) -> date:
    day = TODAY - timedelta(days=20)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _future_sunday() -> date:
    return TODAY + timedelta(days=(6 - TODAY.weekday()) % 7 + 7)


def _post(client, pm, employees, dates, status="leave", **over):
    body = {
        "employee_ids": [str(e.id if hasattr(e, "id") else e) for e in employees],
        "dates": [d.isoformat() for d in dates],
        "status": status,
    }
    body.update(over)
    return client.post(URL, headers=pm, json=body)


def _apply(client, pm, employees, dates, status="leave", **over):
    res = _post(client, pm, employees, dates, status, dry_run=False, **over)
    assert res.status_code == 200, res.text
    return res.json()


def _outcomes(body) -> list[tuple[str, str, str]]:
    return [
        (r["employee_id"], r["attendance_date"], r["outcome"]) for r in body["results"]
    ]


def _rows(db):
    db.expire_all()
    return db.query(AttendanceRecord).order_by(AttendanceRecord.attendance_date).all()


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


def _employee_with_login(make_user, make_employee, code):
    user = make_user(f"{code.lower()}@x.com", role=UserRole.employee)
    return make_employee(employee_code=code, user_id=user.id), user


# ---------------------------------------------------------------------------
# Preview vs apply
# ---------------------------------------------------------------------------


def test_preview_reports_outcomes_and_writes_nothing(client, pm, make_employee, db):
    e = make_employee(employee_code="BP-1")
    d1, d2 = _working(db, 10), _working(db, 11)
    res = _post(client, pm, [e], [d1, d2])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["dry_run"] is True
    assert body["bulk_action_id"] is None
    assert body["summary"]["created"] == 2
    assert [r["outcome"] for r in body["results"]] == ["created", "created"]
    assert body["results"][0]["employee_code"] == "BP-1"
    assert _rows(db) == []
    assert db.query(AuditLog).filter(AuditLog.action.like("attendance.%")).count() == 0
    assert db.query(Notification).count() == 0


def test_dry_run_is_the_default(client, pm, make_employee, db):
    e = make_employee(employee_code="BP-2")
    res = client.post(
        URL,
        headers=pm,
        json={
            "employee_ids": [str(e.id)],
            "dates": [_working(db, 10).isoformat()],
            "status": "leave",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["dry_run"] is True
    assert _rows(db) == []


def test_preview_and_apply_agree(client, pm, make_employee, make_attendance, db):
    e = make_employee(employee_code="BP-3")
    d1, d2, d3 = _working(db, 10), _working(db, 11), _working(db, 12)
    make_attendance(employee_id=e.id, attendance_date=d2, status=AttendanceStatus.present)
    make_attendance(employee_id=e.id, attendance_date=d3, status=AttendanceStatus.leave)

    preview = _post(client, pm, [e], [d1, d2, d3]).json()
    applied = _apply(client, pm, [e], [d1, d2, d3])
    assert [r["outcome"] for r in preview["results"]] == ["created", "updated", "unchanged"]
    assert _outcomes(preview) == _outcomes(applied)
    assert applied["bulk_action_id"] is not None
    assert [r.status for r in _rows(db)] == [AttendanceStatus.leave] * 3


def test_one_employee_many_dates_and_many_employees_one_date(
    client, pm, make_employee, db
):
    a = make_employee(employee_code="BP-4A")
    b = make_employee(employee_code="BP-4B")
    c = make_employee(employee_code="BP-4C")
    d1, d2, d3 = _working(db, 10), _working(db, 11), _working(db, 12)

    one_many = _apply(client, pm, [a], [d1, d2, d3], status="comp_off")
    assert one_many["summary"]["created"] == 3
    many_one = _apply(client, pm, [b, c], [d1], status="holiday")
    assert many_one["summary"]["created"] == 2
    assert len(_rows(db)) == 5


# ---------------------------------------------------------------------------
# Every status on a future date; status only
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ALL_STATUSES)
def test_every_status_can_be_bulk_planned_for_a_future_date(
    client, pm, make_employee, db, status
):
    e = make_employee(employee_code=f"BS-{status}")
    day = _working(db, 10)
    body = _apply(client, pm, [e], [day], status=status)
    assert body["summary"]["created"] == 1, body
    [row] = _rows(db)
    assert row.status.value == status
    assert row.check_in_at is None and row.check_out_at is None
    # Leave charge follows the status by the existing rule.
    if status == "absent":
        assert row.leave_day_fraction == Decimal("1.00")
    else:
        assert row.leave_day_fraction is None


def test_existing_times_and_permission_are_never_overwritten(
    client, pm, make_employee, make_attendance, make_permission_request, db
):
    from datetime import datetime, timezone

    e = make_employee(employee_code="BS-T")
    day = _past_working(db)
    check_in = datetime(day.year, day.month, day.day, 3, 30, tzinfo=timezone.utc)
    check_out = datetime(day.year, day.month, day.day, 12, 0, tzinfo=timezone.utc)
    rec = make_attendance(
        employee_id=e.id,
        attendance_date=day,
        status=AttendanceStatus.present,
        check_in_at=check_in,
        check_out_at=check_out,
        total_minutes=510,
    )
    perm = make_permission_request(
        employee_id=e.id, permission_date=day, status=PermissionStatus.approved
    )

    body = _apply(client, pm, [e], [day], status="half_day", note="Left early.")
    [result] = body["results"]
    assert result["outcome"] == "updated"
    db.expire_all()
    row = db.get(AttendanceRecord, rec.id)
    assert row.status == AttendanceStatus.half_day
    assert (row.check_in_at, row.check_out_at, row.total_minutes) == (
        check_in, check_out, 510,
    )
    assert row.note == "Left early."
    kept = db.get(PermissionRequest, perm.id)
    assert kept.status == PermissionStatus.approved
    assert db.query(PermissionRequest).count() == 1

    # A non-worked status on a timed day says the times are kept.
    body = _apply(client, pm, [e], [day], status="leave", note="Was on leave.")
    codes = [w["code"] for w in body["results"][0]["warnings"]]
    assert "existing_times_kept" in codes


# ---------------------------------------------------------------------------
# Past dates need a reason
# ---------------------------------------------------------------------------


def test_past_pairs_without_a_reason_are_rejected_while_future_ones_apply(
    client, pm, make_employee, db
):
    e = make_employee(employee_code="BR-1")
    past, future = _past_working(db), _working(db, 10)
    body = _apply(client, pm, [e], [past, future], status="absent")
    by_date = {r["attendance_date"]: r for r in body["results"]}
    assert by_date[past.isoformat()]["outcome"] == "rejected"
    assert by_date[past.isoformat()]["reason_code"] == "reason_required"
    assert by_date[future.isoformat()]["outcome"] == "created"
    assert [r.attendance_date for r in _rows(db)] == [future]


def test_past_pairs_apply_with_a_reason(client, pm, make_employee, make_attendance, db):
    e = make_employee(employee_code="BR-2")
    past = _past_working(db)
    make_attendance(
        employee_id=e.id, attendance_date=past, status=AttendanceStatus.present
    )
    body = _apply(client, pm, [e], [past], status="leave", note="  Sick, phoned in.  ")
    assert body["results"][0]["outcome"] == "updated"
    [row] = _rows(db)
    assert row.note == "Sick, phoned in."


def test_whitespace_reason_is_no_reason(client, pm, make_employee, db):
    e = make_employee(employee_code="BR-3")
    body = _apply(client, pm, [e], [_past_working(db)], note="   ")
    assert body["results"][0]["reason_code"] == "reason_required"


def test_unchanged_past_pair_needs_no_reason(
    client, pm, make_employee, make_attendance, db
):
    e = make_employee(employee_code="BR-4")
    past = _past_working(db)
    make_attendance(employee_id=e.id, attendance_date=past, status=AttendanceStatus.leave)
    body = _apply(client, pm, [e], [past], status="leave")
    assert body["results"][0]["outcome"] == "unchanged"


# ---------------------------------------------------------------------------
# Authorization and per-pair validation
# ---------------------------------------------------------------------------


def test_only_a_project_manager_can_bulk_apply(client, auth_header, make_employee, db):
    e = make_employee(employee_code="BA-1")
    emp = auth_header("emp-bulk@x.com", role=UserRole.employee)
    res = _post(client, emp, [e], [_working(db, 10)], dry_run=False)
    assert res.status_code == 403, res.text
    assert _rows(db) == []


def test_unauthenticated_is_refused(client, make_employee, db):
    e = make_employee(employee_code="BA-2")
    res = client.post(
        URL,
        json={"employee_ids": [str(e.id)], "dates": [TODAY.isoformat()], "status": "leave"},
    )
    assert res.status_code == 401


def test_every_pair_is_validated(client, pm, make_employee, db):
    import uuid as _uuid
    from datetime import datetime, timezone

    ok = make_employee(employee_code="BA-OK")
    deleted = make_employee(employee_code="BA-DEL")
    deleted.deleted_at = datetime.now(timezone.utc)
    exited = make_employee(employee_code="BA-EXIT", status=EmployeeStatus.exited)
    joiner = make_employee(employee_code="BA-NEW")
    day = _working(db, 10)
    joiner.date_of_joining = day + timedelta(days=30)
    db.commit()
    ghost = _uuid.uuid4()

    body = _apply(client, pm, [ok, deleted, exited, joiner, ghost], [day])
    codes = {r["employee_id"]: (r["outcome"], r["reason_code"]) for r in body["results"]}
    assert codes[str(ok.id)] == ("created", None)
    assert codes[str(deleted.id)] == ("rejected", "employee_not_found")
    assert codes[str(ghost)] == ("rejected", "employee_not_found")
    assert codes[str(exited.id)] == ("rejected", "employee_exited")
    assert codes[str(joiner.id)] == ("rejected", "before_joining")
    assert body["summary"] == {
        "created": 1, "updated": 0, "unchanged": 0, "protected": 0, "rejected": 4,
    }
    assert len(_rows(db)) == 1


def test_an_exited_employee_can_still_have_a_past_day_corrected(
    client, pm, make_employee, db
):
    e = make_employee(employee_code="BA-EX2", status=EmployeeStatus.exited)
    body = _apply(client, pm, [e], [_past_working(db)], note="Back-filled.")
    assert body["results"][0]["outcome"] == "created"


@pytest.mark.parametrize(
    "body",
    [
        {"employee_ids": [], "dates": ["2026-12-01"], "status": "leave"},
        {"employee_ids": ["00000000-0000-0000-0000-000000000001"], "dates": [],
         "status": "leave"},
        {"employee_ids": ["00000000-0000-0000-0000-000000000001"],
         "dates": ["2026-12-01"], "status": "not_a_status"},
        {"employee_ids": ["00000000-0000-0000-0000-000000000001"],
         "dates": ["2026-12-01"], "status": "leave", "note": "x" * 501},
    ],
)
def test_malformed_requests_are_refused(client, pm, body):
    assert client.post(URL, headers=pm, json=body).status_code == 422


def test_oversized_action_is_refused(client, pm):
    import uuid as _uuid

    body = {
        "employee_ids": [str(_uuid.uuid4()) for _ in range(20)],
        "dates": [(TODAY + timedelta(days=i)).isoformat() for i in range(26)],
        "status": "leave",
    }
    assert client.post(URL, headers=pm, json=body).status_code == 422


# ---------------------------------------------------------------------------
# Non-working days
# ---------------------------------------------------------------------------


def test_non_working_days_are_rejected_by_default_and_reported(
    client, pm, make_employee, db
):
    e = make_employee(employee_code="BN-1")
    sunday, workday = _future_sunday(), _working(db, 10)
    body = _apply(client, pm, [e], [sunday, workday], status="leave")
    by_date = {r["attendance_date"]: r for r in body["results"]}
    assert by_date[sunday.isoformat()]["outcome"] == "rejected"
    assert by_date[sunday.isoformat()]["reason_code"] == "non_working_day"
    assert by_date[workday.isoformat()]["outcome"] == "created"
    assert [r.attendance_date for r in _rows(db)] == [workday]


def test_include_non_working_applies_them(client, pm, make_employee, db):
    e = make_employee(employee_code="BN-2")
    sunday = _future_sunday()
    body = _apply(
        client, pm, [e], [sunday], status="comp_off", include_non_working=True
    )
    assert body["results"][0]["outcome"] == "created"
    assert [r.attendance_date for r in _rows(db)] == [sunday]


# ---------------------------------------------------------------------------
# Records written by approved leave
# ---------------------------------------------------------------------------


def _approved_leave(db, make_leave_request, employee, start, end, status=LeaveStatus.approved):
    actor = db.execute(select(User).where(User.email == "pm-bulk@x.com")).scalar_one()
    req = make_leave_request(employee_id=employee.id, start_date=start, end_date=end)
    apply_leave_approved(db, actor, req)
    req.status = status
    db.commit()
    return req, actor


@pytest.mark.parametrize(
    "leave_status", [LeaveStatus.approved, LeaveStatus.cancellation_requested]
)
def test_live_leave_approval_rows_are_protected_and_stay_cancellable(
    client, pm, make_employee, make_leave_request, db, leave_status
):
    e = make_employee(employee_code=f"BL-{leave_status.value}")
    day = _working(db, 10)
    req, actor = _approved_leave(db, make_leave_request, e, day, day, leave_status)

    body = _apply(client, pm, [e], [day], status="present")
    [result] = body["results"]
    assert (result["outcome"], result["reason_code"]) == ("protected", "leave_approval")
    [row] = _rows(db)
    assert row.status == AttendanceStatus.leave

    # Still exactly the row the cancellation removes.
    db.refresh(req)
    effect = reverse_leave_approved(db, actor, req)
    db.commit()
    assert effect.days == [day]
    assert _rows(db) == []


def test_half_day_leave_approval_row_is_protected(
    client, pm, make_employee, make_leave_request, db
):
    from app.modules.leave.models import LeaveHalfDayPeriod

    e = make_employee(employee_code="BL-HALF")
    day = _working(db, 10)
    actor = db.execute(select(User).where(User.email == "pm-bulk@x.com")).scalar_one()
    req = make_leave_request(employee_id=e.id, start_date=day, end_date=day)
    req.half_day_period = list(LeaveHalfDayPeriod)[0]
    db.commit()
    apply_leave_approved(db, actor, req)
    req.status = LeaveStatus.approved
    db.commit()

    body = _apply(client, pm, [e], [day], status="absent")
    assert body["results"][0]["outcome"] == "protected"


def test_a_leave_row_no_longer_live_is_an_ordinary_record(
    client, pm, make_employee, make_leave_request, db
):
    """A row whose request was cancelled/rejected (and so would never be
    removed by a cancellation) is not protected."""
    e = make_employee(employee_code="BL-DEAD")
    day = _working(db, 10)
    _approved_leave(db, make_leave_request, e, day, day, LeaveStatus.cancelled)
    body = _apply(client, pm, [e], [day], status="present")
    assert body["results"][0]["outcome"] == "updated"


def test_a_pm_edited_leave_row_is_an_ordinary_record(
    client, pm, make_employee, make_leave_request, db
):
    from datetime import datetime, timezone

    e = make_employee(employee_code="BL-EDIT")
    day = _past_working(db)
    _approved_leave(db, make_leave_request, e, day, day)
    [row] = _rows(db)
    row.check_in_at = datetime(day.year, day.month, day.day, 4, 0, tzinfo=timezone.utc)
    db.commit()
    body = _apply(client, pm, [e], [day], status="present", note="Came in after all.")
    assert body["results"][0]["outcome"] == "updated"


def test_preview_warns_that_present_blocks_a_pending_leave(
    client, pm, make_employee, make_leave_request, db
):
    e = make_employee(employee_code="BL-PEND")
    day = _working(db, 10)
    make_leave_request(employee_id=e.id, start_date=day, end_date=day)
    body = _post(client, pm, [e], [day], status="present").json()
    [result] = body["results"]
    assert result["outcome"] == "created"
    assert [w["code"] for w in result["warnings"]] == ["pending_leave_request"]
    # Not a worked status: no warning.
    body = _post(client, pm, [e], [day], status="comp_off").json()
    assert body["results"][0]["warnings"] == []


# ---------------------------------------------------------------------------
# Partial failure, duplicates, repeated submissions, concurrency
# ---------------------------------------------------------------------------


def test_partial_success_reports_every_pair(client, pm, make_employee, make_attendance, db):
    import uuid as _uuid

    a = make_employee(employee_code="BX-A")
    b = make_employee(employee_code="BX-B")
    day = _working(db, 10)
    make_attendance(employee_id=b.id, attendance_date=day, status=AttendanceStatus.present)
    ghost = _uuid.uuid4()
    body = _apply(client, pm, [a, b, ghost], [day, _future_sunday()], status="leave")
    # 3 employees x 2 dates = 6 results, none dropped.
    assert len(body["results"]) == 6
    assert body["summary"] == {
        "created": 1, "updated": 1, "unchanged": 0, "protected": 0, "rejected": 4,
    }
    for r in body["results"]:
        if r["outcome"] == "rejected":
            assert r["reason_code"] and r["message"]


def test_duplicate_pairs_in_one_request_are_written_once_and_reported(
    client, pm, make_employee, db
):
    e = make_employee(employee_code="BD-1")
    day = _working(db, 10)
    body = _apply(client, pm, [e, e], [day, day], status="leave")
    outcomes = [(r["outcome"], r["reason_code"]) for r in body["results"]]
    assert outcomes[0] == ("created", None)
    assert outcomes[1:] == [("rejected", "duplicate_in_request")] * 3
    assert len(_rows(db)) == 1
    [row] = _rows(db)
    assert len(_audits(db, row.id)) == 1


def test_repeated_submission_is_idempotent(client, pm, make_user, make_employee, db):
    e, _ = _employee_with_login(make_user, make_employee, "BD-REP")
    days = [_working(db, 10), _working(db, 11)]
    first = _apply(client, pm, [e], days, status="leave")
    assert first["summary"]["created"] == 2
    audits_before = db.query(AuditLog).count()
    notes_before = db.query(Notification).count()

    second = _apply(client, pm, [e], days, status="leave")
    assert second["summary"]["unchanged"] == 2
    assert db.query(AuditLog).count() == audits_before
    assert db.query(Notification).count() == notes_before
    assert len(_rows(db)) == 2


def test_a_concurrent_insert_rejects_only_that_pair(
    client, pm, make_employee, make_attendance, db, monkeypatch
):
    """Somebody else inserts a row for one pair after the action read the day.
    That pair's savepoint is rolled back and reported; the others still apply."""
    a = make_employee(employee_code="BC-A")
    b = make_employee(employee_code="BC-B")
    day = _working(db, 10)
    raced = make_attendance(
        employee_id=a.id, attendance_date=day, status=AttendanceStatus.present
    )
    # The action's read misses the racing row, as if it landed just after.
    monkeypatch.setattr(bulk_module, "_load_existing", lambda *a, **k: {})

    body = _apply(client, pm, [a, b], [day], status="leave")
    by_emp = {r["employee_id"]: r for r in body["results"]}
    assert by_emp[str(a.id)]["outcome"] == "rejected"
    assert by_emp[str(a.id)]["reason_code"] == "concurrent_change"
    assert by_emp[str(b.id)]["outcome"] == "created"

    db.expire_all()
    assert db.get(AttendanceRecord, raced.id).status == AttendanceStatus.present
    statuses = {r.employee_id: r.status for r in _rows(db)}
    assert statuses == {a.id: AttendanceStatus.present, b.id: AttendanceStatus.leave}
    # No audit entry for the rolled-back pair.
    assert _audits(db, raced.id) == []


def test_apply_locks_the_rows_it_reads(make_employee, make_attendance, db):
    """The apply path re-reads existing rows FOR UPDATE; the preview does not."""
    e = make_employee(employee_code="BC-LOCK")
    day = _working(db, 10)
    make_attendance(employee_id=e.id, attendance_date=day)
    captured = []

    from sqlalchemy import event

    @event.listens_for(db.get_bind(), "before_cursor_execute")
    def _capture(conn, cursor, statement, *args):
        captured.append(statement)

    try:
        bulk_module._load_existing(db, [e.id], [day], lock=True)
        bulk_module._load_existing(db, [e.id], [day], lock=False)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", _capture)
        db.rollback()
    selects = [s for s in captured if "attendance_records" in s]
    assert "FOR UPDATE" in selects[0]
    assert "FOR UPDATE" not in selects[1]


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_each_changed_pair_gets_its_own_bulk_audit_entry(
    client, pm, make_employee, make_attendance, db
):
    e = make_employee(employee_code="BAU-1")
    past = _past_working(db)
    future = _working(db, 10)
    existing = make_attendance(
        employee_id=e.id, attendance_date=past, status=AttendanceStatus.half_day,
        leave_day_fraction=Decimal("0.5"),
    )
    body = _apply(
        client, pm, [e], [past, future], status="absent", note="No show."
    )
    action_id = body["bulk_action_id"]

    [update_audit] = _audits(db, existing.id)
    d = update_audit.details
    assert update_audit.action == "attendance.record.update"
    assert (d["previous_status"], d["status"]) == ("half_day", "absent")
    assert d["previous_leave_day_fraction"] == 0.5
    assert d["leave_day_fraction"] == 1.0
    assert d["note"] == "No show."
    assert d["source"] == "bulk"
    assert d["retrospective"] is True
    assert d["bulk_action_id"] == action_id

    created_id = next(
        r["record_id"] for r in body["results"] if r["attendance_date"] == future.isoformat()
    )
    [create_audit] = _audits(db, created_id)
    assert create_audit.action == "attendance.record.create"
    assert create_audit.details["source"] == "bulk"
    assert create_audit.details["retrospective"] is False
    assert create_audit.details["bulk_action_id"] == action_id


def test_rejected_protected_and_unchanged_pairs_write_no_audit(
    client, pm, make_employee, make_attendance, make_leave_request, db
):
    e = make_employee(employee_code="BAU-2")
    d1, d2 = _working(db, 10), _working(db, 11)
    _approved_leave(db, make_leave_request, e, d1, d1)
    make_attendance(employee_id=e.id, attendance_date=d2, status=AttendanceStatus.leave)
    before = db.query(AuditLog).count()
    body = _apply(client, pm, [e], [d1, d2, _future_sunday()], status="leave")
    assert [r["outcome"] for r in body["results"]] == ["protected", "unchanged", "rejected"]
    assert db.query(AuditLog).count() == before


# ---------------------------------------------------------------------------
# Notifications: one summary per employee per action
# ---------------------------------------------------------------------------


def _notifications(db, user_id):
    db.expire_all()
    return db.query(Notification).filter(Notification.user_id == user_id).all()


def test_one_summary_notification_per_employee(client, pm, make_user, make_employee, db):
    a, ua = _employee_with_login(make_user, make_employee, "BNT-A")
    b, ub = _employee_with_login(make_user, make_employee, "BNT-B")
    days = [_working(db, 10), _working(db, 11), _working(db, 12)]

    _apply(client, pm, [a, b], days, status="leave")
    [na] = _notifications(db, ua.id)
    [nb] = _notifications(db, ub.id)
    assert na.title == "Attendance updated for 3 days"
    assert na.type == "attendance_recorded"
    assert na.message.count("Leave") == 3
    assert na.target_url == f"/attendance?att_month={days[0]:%Y-%m}"
    assert nb.title == "Attendance updated for 3 days"


def test_summary_names_changes_from_a_previous_status(
    client, pm, make_user, make_employee, make_attendance, db
):
    e, u = _employee_with_login(make_user, make_employee, "BNT-C")
    day = _working(db, 10)
    make_attendance(employee_id=e.id, attendance_date=day, status=AttendanceStatus.leave)
    _apply(client, pm, [e], [day], status="present")
    [n] = _notifications(db, u.id)
    assert n.type == "attendance_changed"
    assert "Leave -> Present" in n.message
    assert n.title == "Attendance updated for 1 day"


def test_present_only_actions_stay_silent(client, pm, make_user, make_employee, db):
    e, u = _employee_with_login(make_user, make_employee, "BNT-D")
    _apply(client, pm, [e], [_working(db, 10), _working(db, 11)], status="present")
    assert _notifications(db, u.id) == []


def test_preview_sends_no_notification(client, pm, make_user, make_employee, db):
    e, u = _employee_with_login(make_user, make_employee, "BNT-E")
    _post(client, pm, [e], [_working(db, 10)], status="leave")
    assert _notifications(db, u.id) == []


# ---------------------------------------------------------------------------
# Automatic reports: unchanged schedule, nothing at save time
# ---------------------------------------------------------------------------


def _reports(db, employee_id, day):
    db.expire_all()
    return (
        db.query(DailyWorkReport)
        .filter(
            DailyWorkReport.employee_id == employee_id,
            DailyWorkReport.report_date == day,
        )
        .all()
    )


def test_bulk_future_leave_generates_no_report_until_the_sweep_reaches_it(
    client, pm, make_employee, db
):
    e = make_employee(employee_code="BRP-1")
    day = _working(db, 10)
    _apply(client, pm, [e], [day], status="leave")
    assert _reports(db, e.id, day) == []

    generate_auto_leave_reports(db, today=TODAY)
    assert _reports(db, e.id, day) == []

    generate_auto_leave_reports(db, today=day)
    [report] = _reports(db, e.id, day)
    assert report.origin == ReportOrigin.auto
    assert report.day_status == DayStatus.leave


def test_bulk_still_reconciles_an_auto_report_the_day_no_longer_backs(
    client, pm, make_employee, make_attendance, db
):
    e = make_employee(employee_code="BRP-2")
    past = _past_working(db)
    make_attendance(employee_id=e.id, attendance_date=past, status=AttendanceStatus.leave)
    generate_auto_leave_reports(db, today=past)
    assert len(_reports(db, e.id, past)) == 1

    _apply(client, pm, [e], [past], status="present", note="Was in the office.")
    assert _reports(db, e.id, past) == []
