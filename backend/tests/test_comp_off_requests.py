"""Comp Off Phase 3 - request, validation and PM decision workflow.

The service's business date is frozen to TODAY (a Wednesday) so the calendar
facts below are fixed regardless of when the suite runs.

    docker exec wms-backend-1 pytest tests/test_comp_off_requests.py
"""
import threading
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.audit.models import AuditLog
from app.modules.calendar.models import CalendarEvent, CalendarEventType
from app.modules.comp_off import service
from app.modules.comp_off.models import CompOffRequest, CompOffStatus
from app.modules.leave.models import LeaveRequest, LeaveStatus, LeaveType
from app.modules.permissions.models import PermissionRequest, PermissionStatus
from app.modules.users.models import UserRole
from app.modules.work_reports.models import (
    DailyWorkReport,
    DayStatus,
    ReportOrigin,
    WorkReportStatus,
    WorkReportTask,
)

API = "/api/v1/comp-off-requests"

TODAY = date(2027, 3, 10)        # Wednesday
SUN = date(2027, 3, 7)           # Sunday - non-working
SUN_PREV = date(2027, 2, 28)     # Sunday - non-working
SUN_OLDER = date(2027, 2, 21)    # Sunday - non-working
SAT_1ST = date(2027, 3, 6)       # 1st Saturday - a WORKING day
SAT_2ND = date(2027, 3, 13)      # 2nd Saturday - non-working
THU = date(2027, 3, 4)           # ordinary working Thursday
WED_PAST = date(2027, 3, 3)      # ordinary working Wednesday
MON = date(2027, 3, 15)          # future working day - the day off
TUE = date(2027, 3, 16)          # future working day


@pytest.fixture(autouse=True)
def _frozen_today(monkeypatch):
    monkeypatch.setattr(service, "_today", lambda: TODAY)


@pytest.fixture()
def team(make_user, make_employee, make_project):
    pm_u = make_user("pm@x.com", role=UserRole.project_manager)
    pm = make_employee(employee_code="PM1", user_id=pm_u.id, first_name="Priya", last_name="PM")
    pm2_u = make_user("pm2@x.com", role=UserRole.project_manager)
    pm2 = make_employee(employee_code="PM2", user_id=pm2_u.id)
    emp_u = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E1", user_id=emp_u.id, first_name="Ravi", last_name="K")
    other_u = make_user("other@x.com", role=UserRole.employee)
    other = make_employee(employee_code="E2", user_id=other_u.id)
    project = make_project(code="P1", head_employee_id=other.id)
    return {"pm": pm, "pm2": pm2, "emp": emp, "other": other, "project": project}


def _report(db, employee, day, *, project=None, status=WorkReportStatus.submitted,
            day_status=DayStatus.work_at_office, origin=ReportOrigin.employee):
    report = DailyWorkReport(
        employee_id=employee.id, report_date=day, status=status, origin=origin,
        day_status=day_status,
        submitted_at=datetime.now(timezone.utc) if status == WorkReportStatus.submitted else None,
    )
    db.add(report)
    db.flush()
    if project is not None:
        db.add(WorkReportTask(report_id=report.id, project_id=project.id,
                              description="Tag extraction"))
    db.commit()
    return report


def _worked(db, team, employee=None, day=SUN):
    """The standard evidence: a submitted report with one project task."""
    return _report(db, employee or team["emp"], day, project=team["project"])


def _file(client, login, worked=SUN, off=MON, who="emp@x.com", reason="Worked shutdown"):
    return client.post(API, headers=login(who), json={
        "worked_date": worked.isoformat(), "off_date": off.isoformat(), "reason": reason,
    })


def _error(res) -> str:
    return res.json()["error"]["message"]


def _seed(db, employee, worked, off, status, reviewer=None):
    decided = status in (CompOffStatus.approved, CompOffStatus.rejected)
    row = CompOffRequest(
        employee_id=employee.id, worked_date=worked, off_date=off, status=status,
        manager_id=reviewer.id if decided and reviewer else None,
        reviewed_at=datetime.now(timezone.utc) if decided else None,
    )
    db.add(row)
    db.commit()
    return row


# -- 1. a valid request ------------------------------------------------------

def test_employee_submits_a_valid_request(client, login, db, team):
    _worked(db, team)
    res = _file(client, login)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "pending"
    assert body["employee_id"] == str(team["emp"].id)
    assert body["worked_date"] == SUN.isoformat() and body["off_date"] == MON.isoformat()
    assert body["manager_id"] is None and body["reviewed_at"] is None
    audit = db.execute(select(AuditLog).where(AuditLog.action == "comp_off.request.submit")).scalar_one()
    assert audit.entity_id == uuid.UUID(body["id"])


def test_the_requester_is_the_caller_not_the_body(client, login, db, team):
    """An `employee_id` in the body is ignored (not part of the schema)."""
    _worked(db, team)
    res = client.post(API, headers=login("emp@x.com"), json={
        "worked_date": SUN.isoformat(), "off_date": MON.isoformat(),
        "employee_id": str(team["other"].id),
    })
    assert res.status_code == 201, res.text
    assert res.json()["employee_id"] == str(team["emp"].id)


def test_a_holiday_on_a_weekday_is_eligible(client, login, db, team):
    db.add(CalendarEvent(event_date=THU, title="Festival", event_type=CalendarEventType.holiday))
    db.commit()
    _worked(db, team, day=THU)
    assert _file(client, login, worked=THU).status_code == 201


def test_a_user_without_an_employee_profile_cannot_submit(client, auth_header):
    res = client.post(API, headers=auth_header("noprofile@x.com"), json={
        "worked_date": SUN.isoformat(), "off_date": MON.isoformat()})
    assert res.status_code == 422
    assert "employee profile" in _error(res)


# -- 2. evidence -------------------------------------------------------------

def test_no_report_is_no_evidence(client, login, team):
    res = _file(client, login)
    assert res.status_code == 422
    assert "No submitted work report" in _error(res)


def test_an_auto_week_off_report_is_not_evidence(client, login, db, team):
    _report(db, team["emp"], SUN, day_status=DayStatus.week_off, origin=ReportOrigin.auto)
    assert _file(client, login).status_code == 422


def test_an_auto_report_edited_to_carry_real_tasks_is_evidence(client, login, db, team):
    _report(db, team["emp"], SUN, project=team["project"], origin=ReportOrigin.auto)
    assert _file(client, login).status_code == 201


def test_a_draft_report_is_not_evidence(client, login, db, team):
    _report(db, team["emp"], SUN, project=team["project"], status=WorkReportStatus.draft)
    assert _file(client, login).status_code == 422


def test_someone_elses_report_is_not_evidence(client, login, db, team):
    _worked(db, team, employee=team["other"])
    assert _file(client, login).status_code == 422


def test_attendance_ruled_absent_contradicts_the_worked_day(client, login, db, team):
    _worked(db, team)
    db.add(AttendanceRecord(employee_id=team["emp"].id, attendance_date=SUN,
                            status=AttendanceStatus.absent, total_minutes=0, overtime_minutes=0))
    db.commit()
    res = _file(client, login)
    assert res.status_code == 422 and "absent" in _error(res)


# -- 3/4. calendar eligibility -----------------------------------------------

@pytest.mark.parametrize("day", [WED_PAST, SAT_1ST])
def test_a_working_day_is_not_eligible(client, login, db, team, day):
    _worked(db, team, day=day)
    res = _file(client, login, worked=day)
    assert res.status_code == 422 and "was a working day" in _error(res)


def test_a_sunday_reopened_as_a_working_day_is_not_eligible(client, login, db, team):
    db.add(CalendarEvent(event_date=SUN, title="Make-up day", event_type=CalendarEventType.working_day))
    db.commit()
    _worked(db, team)
    res = _file(client, login)
    assert res.status_code == 422 and "was a working day" in _error(res)


def test_the_day_off_must_be_a_working_day(client, login, db, team):
    _worked(db, team)
    res = _file(client, login, off=SAT_2ND)
    assert res.status_code == 422 and "not a working day" in _error(res)


# -- 5/6. date rules ---------------------------------------------------------

@pytest.mark.parametrize("off", [TODAY, WED_PAST])
def test_off_date_today_or_past_is_refused(client, login, db, team, off):
    _worked(db, team)
    res = _file(client, login, off=off)
    assert res.status_code == 422 and "before the day off" in _error(res)


def test_a_worked_date_in_the_future_is_refused(client, login, db, team):
    res = _file(client, login, worked=date(2027, 3, 14), off=MON)
    assert res.status_code == 422 and "hasn't happened yet" in _error(res)


def test_same_worked_and_off_date_is_refused(client, login, team):
    assert _file(client, login, worked=MON, off=MON).status_code == 422


# -- 7/8/9. conflicts --------------------------------------------------------

def test_a_live_worked_date_cannot_be_reused(client, login, db, team):
    _worked(db, team)
    assert _file(client, login, off=MON).status_code == 201
    res = _file(client, login, off=TUE)
    assert res.status_code == 422 and "existing pending comp off" in _error(res)


def test_a_live_off_date_cannot_be_reused(client, login, db, team):
    _worked(db, team)
    _worked(db, team, day=SUN_PREV)
    assert _file(client, login, worked=SUN).status_code == 201
    assert _file(client, login, worked=SUN_PREV, off=MON).status_code == 422


def test_a_live_requests_off_date_cannot_become_a_worked_date(client, login, db, team):
    _seed(db, team["emp"], SUN_OLDER, SUN, CompOffStatus.approved, team["pm"])
    _worked(db, team)
    res = _file(client, login, worked=SUN, off=MON)
    assert res.status_code == 422 and "existing approved comp off" in _error(res)


@pytest.mark.parametrize("status", [LeaveStatus.pending, LeaveStatus.approved])
def test_leave_on_the_off_date_conflicts(client, login, db, team, status):
    _worked(db, team)
    db.add(LeaveRequest(employee_id=team["emp"].id, leave_type=LeaveType.other,
                        start_date=MON, end_date=TUE, status=status))
    db.commit()
    res = _file(client, login)
    assert res.status_code == 422 and "leave request already covers" in _error(res)


def test_an_attendance_record_on_the_off_date_conflicts(client, login, db, team):
    _worked(db, team)
    db.add(AttendanceRecord(employee_id=team["emp"].id, attendance_date=MON,
                            status=AttendanceStatus.present, total_minutes=0, overtime_minutes=0))
    db.commit()
    res = _file(client, login)
    assert res.status_code == 422 and "already recorded" in _error(res)


def test_a_permission_on_the_off_date_conflicts(client, login, db, team):
    _worked(db, team)
    db.add(PermissionRequest(employee_id=team["emp"].id, permission_date=MON,
                             duration_hours=1, status=PermissionStatus.pending))
    db.commit()
    res = _file(client, login)
    assert res.status_code == 422 and "permission" in _error(res)


def test_rejected_and_cancelled_history_does_not_block(client, login, db, team):
    _seed(db, team["emp"], SUN, MON, CompOffStatus.rejected, team["pm"])
    _seed(db, team["emp"], SUN, MON, CompOffStatus.cancelled)
    _worked(db, team)
    assert _file(client, login).status_code == 201


def test_concurrent_submissions_for_one_worked_date_produce_one_request(client, login, db, team):
    _worked(db, team)
    headers = login("emp@x.com")
    results: list[int] = []
    barrier = threading.Barrier(2)

    def submit(off):
        barrier.wait()
        results.append(client.post(API, headers=headers, json={
            "worked_date": SUN.isoformat(), "off_date": off.isoformat()}).status_code)

    threads = [threading.Thread(target=submit, args=(d,)) for d in (MON, TUE)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(results)[0] == 201 and sorted(results)[1] in (409, 422), results
    assert db.query(CompOffRequest).count() == 1


# -- 10/11/12/13. access and authority ---------------------------------------

@pytest.fixture()
def pending(client, login, db, team):
    _worked(db, team)
    res = _file(client, login)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_employees_see_only_their_own_requests(client, login, db, team, pending):
    _worked(db, team, employee=team["other"])
    assert _file(client, login, who="other@x.com", off=TUE).status_code == 201
    mine = client.get(API, headers=login("emp@x.com")).json()
    assert mine["total"] == 1 and mine["items"][0]["id"] == pending
    res = client.get(f"{API}/{pending}", headers=login("other@x.com"))
    assert res.status_code == 403


def test_a_pm_lists_and_reads_every_request(client, login, db, team, pending):
    _worked(db, team, employee=team["other"])
    assert _file(client, login, who="other@x.com", off=TUE).status_code == 201
    page = client.get(API, headers=login("pm@x.com")).json()
    assert page["total"] == 2
    detail = client.get(f"{API}/{pending}", headers=login("pm@x.com")).json()
    assert detail["employee_name"] == "Ravi K"


@pytest.mark.parametrize("who", ["emp@x.com", "other@x.com"])
def test_non_pms_cannot_decide(client, login, db, pending, who):
    """`other` is a Project Head - Heads have no comp off authority."""
    for action, body in (("approve", {}), ("reject", {"reason": "No"})):
        res = client.post(f"{API}/{pending}/{action}", headers=login(who), json=body)
        assert res.status_code == 403
    assert db.get(CompOffRequest, uuid.UUID(pending)).status == CompOffStatus.pending


def test_a_pm_cannot_review_their_own_request(client, login, db, team):
    _worked(db, team, employee=team["pm"])
    res = _file(client, login, who="pm@x.com")
    assert res.status_code == 201, res.text
    res = client.post(f"{API}/{res.json()['id']}/approve", headers=login("pm@x.com"), json={})
    assert res.status_code == 403 and "your own" in _error(res)


# -- 14/15/16. decisions -----------------------------------------------------

def test_approval_records_reviewer_time_and_status(client, login, db, team, pending):
    res = client.post(f"{API}/{pending}/approve", headers=login("pm@x.com"), json={"comment": " ok "})
    assert res.status_code == 200, res.text
    row = db.get(CompOffRequest, uuid.UUID(pending))
    assert row.status == CompOffStatus.approved
    assert row.manager_id == team["pm"].id and row.reviewed_at is not None
    assert row.manager_comment == "ok"
    assert db.execute(select(AuditLog).where(AuditLog.action == "comp_off.request.approve")).scalar_one()
    # Phase boundary: approval writes no attendance.
    assert db.query(AttendanceRecord).count() == 0


@pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "   "}])
def test_rejection_needs_a_reason(client, login, db, pending, body):
    res = client.post(f"{API}/{pending}/reject", headers=login("pm@x.com"), json=body)
    assert res.status_code == 422
    row = db.get(CompOffRequest, uuid.UUID(pending))
    assert row.status == CompOffStatus.pending and row.reviewed_at is None


def test_rejection_with_a_reason_is_recorded(client, login, db, team, pending):
    res = client.post(f"{API}/{pending}/reject", headers=login("pm@x.com"),
                      json={"reason": "  Report shows no site work  "})
    assert res.status_code == 200, res.text
    row = db.get(CompOffRequest, uuid.UUID(pending))
    assert row.status == CompOffStatus.rejected
    assert row.manager_comment == "Report shows no site work"
    assert row.manager_id == team["pm"].id and row.reviewed_at is not None


def test_approval_revalidates_the_off_date(client, login, db, team, pending):
    """A PM-planned attendance row on the day off since submission blocks it."""
    db.add(AttendanceRecord(employee_id=team["emp"].id, attendance_date=MON,
                            status=AttendanceStatus.present, total_minutes=0, overtime_minutes=0))
    db.commit()
    res = client.post(f"{API}/{pending}/approve", headers=login("pm@x.com"), json={})
    assert res.status_code == 422
    assert db.get(CompOffRequest, uuid.UUID(pending)).status == CompOffStatus.pending


def test_a_day_off_that_has_passed_cannot_be_approved(client, login, db, team, monkeypatch, pending):
    monkeypatch.setattr(service, "_today", lambda: date(2027, 3, 16))
    res = client.post(f"{API}/{pending}/approve", headers=login("pm@x.com"), json={})
    assert res.status_code == 422 and "already passed" in _error(res)


# -- 17. repeated and concurrent decisions -----------------------------------

def test_a_decided_request_cannot_be_decided_again(client, login, db, team, pending):
    pm = login("pm@x.com")
    assert client.post(f"{API}/{pending}/approve", headers=pm, json={}).status_code == 200
    first = db.get(CompOffRequest, uuid.UUID(pending))
    reviewed_at = first.reviewed_at
    for action, body, who in (("approve", {}, "pm2@x.com"), ("reject", {"reason": "x"}, "pm2@x.com")):
        res = client.post(f"{API}/{pending}/{action}", headers=login(who), json=body)
        assert res.status_code == 409
    db.expire_all()
    row = db.get(CompOffRequest, uuid.UUID(pending))
    assert row.status == CompOffStatus.approved
    assert row.manager_id == team["pm"].id and row.reviewed_at == reviewed_at
    assert client.post(f"{API}/{pending}/cancel", headers=login("emp@x.com")).status_code == 409


def test_concurrent_approve_and_reject_produce_one_winner(client, login, db, pending):
    a, b = login("pm@x.com"), login("pm2@x.com")
    results: dict[str, int] = {}
    barrier = threading.Barrier(2)

    def approve():
        barrier.wait()
        results["approve"] = client.post(f"{API}/{pending}/approve", headers=a, json={}).status_code

    def reject():
        barrier.wait()
        results["reject"] = client.post(f"{API}/{pending}/reject", headers=b,
                                        json={"reason": "No"}).status_code

    threads = [threading.Thread(target=approve), threading.Thread(target=reject)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(results.values()) == [200, 409], results
    row = db.get(CompOffRequest, uuid.UUID(pending))
    winner = next(k for k, v in results.items() if v == 200)
    assert row.status == (CompOffStatus.approved if winner == "approve" else CompOffStatus.rejected)
    decisions = db.execute(select(AuditLog).where(AuditLog.action.in_(
        ("comp_off.request.approve", "comp_off.request.reject")))).scalars().all()
    assert len(decisions) == 1


# -- 18. failed transaction leaves nothing behind ----------------------------

def test_a_failed_approval_leaves_no_partial_decision(client, login, db, pending, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(service, "record_audit", boom)
    with pytest.raises(RuntimeError):
        client.post(f"{API}/{pending}/approve", headers=login("pm@x.com"), json={})
    db.expire_all()
    row = db.get(CompOffRequest, uuid.UUID(pending))
    assert row.status == CompOffStatus.pending
    assert row.manager_id is None and row.reviewed_at is None and row.manager_comment is None


# -- cancellation of a pending request (author only) -------------------------

def test_the_author_can_cancel_a_pending_request_and_refile(client, login, db, team, pending):
    assert client.post(f"{API}/{pending}/cancel", headers=login("other@x.com")).status_code == 403
    assert client.post(f"{API}/{pending}/cancel", headers=login("pm@x.com")).status_code == 403
    res = client.post(f"{API}/{pending}/cancel", headers=login("emp@x.com"))
    assert res.status_code == 200 and res.json()["status"] == "cancelled"
    assert _file(client, login).status_code == 201


# -- negative cases and traceability ------------------------------------------

def test_every_route_requires_authentication(client):
    some_id = uuid.uuid4()
    for method, path in (
        ("get", API), ("post", API), ("get", f"{API}/{some_id}"),
        ("post", f"{API}/{some_id}/approve"), ("post", f"{API}/{some_id}/reject"),
        ("post", f"{API}/{some_id}/cancel"),
    ):
        assert getattr(client, method)(path).status_code == 401, (method, path)


def test_an_unknown_request_is_404(client, login, team):
    missing = uuid.uuid4()
    pm = login("pm@x.com")
    assert client.get(f"{API}/{missing}", headers=pm).status_code == 404
    assert client.post(f"{API}/{missing}/approve", headers=pm, json={}).status_code == 404
    assert client.post(f"{API}/{missing}/reject", headers=pm,
                       json={"reason": "x"}).status_code == 404


def test_approval_revalidates_the_worked_date_evidence(client, login, db, team, pending):
    """The report backing the request was reopened to draft after submission -
    the PM cannot approve on evidence that no longer stands."""
    report = db.execute(
        select(DailyWorkReport).where(DailyWorkReport.employee_id == team["emp"].id)
    ).scalar_one()
    report.status = WorkReportStatus.draft
    db.commit()
    res = client.post(f"{API}/{pending}/approve", headers=login("pm@x.com"), json={})
    assert res.status_code == 422 and "No submitted work report" in _error(res)
    assert db.get(CompOffRequest, uuid.UUID(pending)).status == CompOffStatus.pending


def test_a_rejection_is_traceable_and_grants_nothing(client, login, db, team, pending):
    res = client.post(f"{API}/{pending}/reject", headers=login("pm@x.com"),
                      json={"reason": "Not site work"})
    assert res.status_code == 200, res.text
    audit = db.execute(
        select(AuditLog).where(AuditLog.action == "comp_off.request.reject")
    ).scalar_one()
    assert audit.entity_id == uuid.UUID(pending)
    assert audit.details["comment"] == "Not site work"
    assert audit.details["status"] == "rejected"
    assert audit.actor_user_id is not None
    # No credit: nothing is written to attendance, and the request cannot be
    # approved afterwards.
    assert db.query(AttendanceRecord).count() == 0
    res = client.post(f"{API}/{pending}/approve", headers=login("pm2@x.com"), json={})
    assert res.status_code == 409


def test_an_approval_audit_names_both_dates(client, login, db, pending):
    client.post(f"{API}/{pending}/approve", headers=login("pm@x.com"), json={})
    audit = db.execute(
        select(AuditLog).where(AuditLog.action == "comp_off.request.approve")
    ).scalar_one()
    assert audit.details["worked_date"] == SUN.isoformat()
    assert audit.details["off_date"] == MON.isoformat()
    assert audit.details["status"] == "approved"


def test_cancellation_is_audited(client, login, db, pending):
    client.post(f"{API}/{pending}/cancel", headers=login("emp@x.com"))
    audit = db.execute(
        select(AuditLog).where(AuditLog.action == "comp_off.request.cancel")
    ).scalar_one()
    assert audit.details["status"] == "cancelled"


def test_list_filters_by_status_and_excludes_self(client, login, db, team, pending):
    _worked(db, team, employee=team["pm"])
    assert _file(client, login, who="pm@x.com", off=TUE).status_code == 201
    pm = login("pm@x.com")
    queue = client.get(API, headers=pm, params={"exclude_self": "true"}).json()
    assert [i["id"] for i in queue["items"]] == [pending]
    client.post(f"{API}/{pending}/approve", headers=login("pm2@x.com"), json={})
    approved = client.get(API, headers=pm, params={"status": "approved"}).json()
    assert approved["total"] == 1 and approved["items"][0]["id"] == pending


def test_an_employee_cannot_list_someone_else_by_filter(client, login, db, team, pending):
    res = client.get(API, headers=login("other@x.com"),
                     params={"employee_id": str(team["emp"].id)})
    assert res.status_code == 200 and res.json()["total"] == 0
