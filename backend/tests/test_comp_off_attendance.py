"""Comp Off Phase 4 - an approved request marks its day off in attendance.

The approval writes ONE `comp_off` row on `off_date`, linked by
`attendance_records.comp_off_request_id` (migration 0088), in the same
transaction as the decision. The service's business date is frozen to TODAY.

    docker exec wms-backend-1 pytest tests/test_comp_off_attendance.py
"""
import threading
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.modules.attendance import service as attendance_service
from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.audit.models import AuditLog
from app.modules.comp_off import service
from app.modules.comp_off.models import CompOffRequest, CompOffStatus
from app.modules.users.models import UserRole
from app.modules.work_reports.models import (
    DailyWorkReport,
    DayStatus,
    ReportOrigin,
    WorkReportStatus,
    WorkReportTask,
)

API = "/api/v1/comp-off-requests"

TODAY = date(2027, 3, 10)   # Wednesday
SUN = date(2027, 3, 7)      # Sunday - the day worked
MON = date(2027, 3, 15)     # future working day - the day off

IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture(autouse=True)
def _frozen_today(monkeypatch):
    monkeypatch.setattr(service, "_today", lambda: TODAY)


@pytest.fixture()
def team(make_user, make_employee, make_project):
    pm_u = make_user("pm@x.com", role=UserRole.project_manager)
    pm = make_employee(employee_code="PM1", user_id=pm_u.id)
    pm2_u = make_user("pm2@x.com", role=UserRole.project_manager)
    make_employee(employee_code="PM2", user_id=pm2_u.id)
    emp_u = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E1", user_id=emp_u.id)
    project = make_project(code="P1")
    return {"pm": pm, "pm_user": pm_u, "emp": emp, "project": project}


@pytest.fixture()
def pending(client, login, db, team):
    """A valid pending request: worked SUN (submitted report + one task), off MON."""
    report = DailyWorkReport(
        employee_id=team["emp"].id, report_date=SUN, status=WorkReportStatus.submitted,
        origin=ReportOrigin.employee, day_status=DayStatus.work_at_office,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(report)
    db.flush()
    db.add(WorkReportTask(report_id=report.id, project_id=team["project"].id,
                          description="Tag extraction"))
    db.commit()
    res = client.post(API, headers=login("emp@x.com"), json={
        "worked_date": SUN.isoformat(), "off_date": MON.isoformat(), "reason": "Shutdown",
    })
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _approve(client, login, req_id, who="pm@x.com"):
    return client.post(f"{API}/{req_id}/approve", headers=login(who), json={})


def _off_rows(db, team):
    db.expire_all()
    return db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.employee_id == team["emp"].id,
            AttendanceRecord.attendance_date == MON,
        )
    ).scalars().all()


def _status(db, req_id) -> CompOffStatus:
    db.expire_all()
    return db.get(CompOffRequest, uuid.UUID(req_id)).status


def _plant_row(db, team, status=AttendanceStatus.present) -> AttendanceRecord:
    row = AttendanceRecord(
        employee_id=team["emp"].id, attendance_date=MON, status=status,
        total_minutes=0, overtime_minutes=0, note="PM planned",
    )
    db.add(row)
    db.commit()
    return row


# -- the day off is written and linked ----------------------------------------

def test_approval_marks_the_day_off_linked_to_the_request(client, login, db, team, pending):
    res = _approve(client, login, pending)
    assert res.status_code == 200, res.text

    (row,) = _off_rows(db, team)
    assert row.status == AttendanceStatus.comp_off
    assert row.comp_off_request_id == uuid.UUID(pending)
    assert row.check_in_at is None and row.check_out_at is None
    assert row.total_minutes == 0
    # Not drawn from the leave pool.
    assert row.leave_day_fraction is None
    assert row.created_by == team["pm_user"].id
    assert "7 March 2027" in row.note


def test_both_audit_entries_reference_each_other(client, login, db, team, pending):
    _approve(client, login, pending)
    (row,) = _off_rows(db, team)

    created = db.execute(
        select(AuditLog).where(
            AuditLog.action == "attendance.record.create", AuditLog.entity_id == row.id
        )
    ).scalar_one()
    assert created.details["source"] == "comp_off_approval"
    assert created.details["comp_off_request_id"] == pending
    assert created.details["status"] == "comp_off"
    assert created.details["attendance_date"] == MON.isoformat()
    assert created.details["worked_date"] == SUN.isoformat()

    decision = db.execute(
        select(AuditLog).where(AuditLog.action == "comp_off.request.approve")
    ).scalar_one()
    assert decision.details["attendance_record_id"] == str(row.id)


def test_the_worked_date_is_left_exactly_as_it_was(client, login, db, team, pending):
    worked = AttendanceRecord(
        employee_id=team["emp"].id, attendance_date=SUN, status=AttendanceStatus.present,
        check_in_at=datetime(2027, 3, 7, 9, 0, tzinfo=IST),
        check_out_at=datetime(2027, 3, 7, 17, 0, tzinfo=IST),
        total_minutes=480, overtime_minutes=0, note="Shutdown work",
    )
    db.add(worked)
    db.commit()
    before = (worked.id, worked.status, worked.check_in_at, worked.note, worked.updated_at)

    assert _approve(client, login, pending).status_code == 200

    db.expire_all()
    after = db.get(AttendanceRecord, worked.id)
    assert (after.id, after.status, after.check_in_at, after.note, after.updated_at) == before
    assert after.comp_off_request_id is None
    reports = db.execute(select(DailyWorkReport).where(
        DailyWorkReport.employee_id == team["emp"].id)).scalars().all()
    assert [r.report_date for r in reports] == [SUN]
    assert db.query(WorkReportTask).count() == 1


# -- atomicity ----------------------------------------------------------------

def test_a_failed_attendance_audit_rolls_the_approval_back(
    client, login, db, team, pending, monkeypatch
):
    def boom(*args, **kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(attendance_service, "_audit_record", boom)
    with pytest.raises(RuntimeError):
        _approve(client, login, pending)
    assert _status(db, pending) == CompOffStatus.pending
    assert _off_rows(db, team) == []


def test_a_failed_decision_audit_leaves_no_day_off(
    client, login, db, team, pending, monkeypatch
):
    """The decision audit runs AFTER the attendance write - its failure must take
    the already-flushed row back with it."""
    def boom(*args, **kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(service, "record_audit", boom)
    with pytest.raises(RuntimeError):
        _approve(client, login, pending)
    assert _status(db, pending) == CompOffStatus.pending
    assert _off_rows(db, team) == []


# -- never twice, never over another decision ---------------------------------

def test_a_repeated_approval_writes_no_second_day(client, login, db, team, pending):
    assert _approve(client, login, pending).status_code == 200
    res = _approve(client, login, pending, who="pm2@x.com")
    assert res.status_code == 409
    assert len(_off_rows(db, team)) == 1


def test_the_database_refuses_a_second_row_for_one_request(client, login, db, team, pending):
    """The UNIQUE link is the guarantee, independent of any service check."""
    _approve(client, login, pending)
    db.add(AttendanceRecord(
        employee_id=team["emp"].id, attendance_date=date(2027, 3, 16),
        status=AttendanceStatus.comp_off, total_minutes=0, overtime_minutes=0,
        comp_off_request_id=uuid.UUID(pending),
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_concurrent_approvals_produce_one_day_off(client, login, db, team, pending):
    a, b = login("pm@x.com"), login("pm2@x.com")
    results: list[int] = []
    barrier = threading.Barrier(2)

    def approve(headers):
        barrier.wait()
        results.append(client.post(f"{API}/{pending}/approve", headers=headers,
                                   json={}).status_code)

    threads = [threading.Thread(target=approve, args=(h,)) for h in (a, b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(results) == [200, 409], results
    assert len(_off_rows(db, team)) == 1
    assert db.execute(select(AuditLog).where(
        AuditLog.action == "comp_off.request.approve")).scalars().all().__len__() == 1


def test_an_existing_row_on_the_day_off_is_not_overwritten(client, login, db, team, pending):
    planted = _plant_row(db, team, AttendanceStatus.leave)
    res = _approve(client, login, pending)
    assert res.status_code == 422, res.text
    assert _status(db, pending) == CompOffStatus.pending
    (row,) = _off_rows(db, team)
    assert row.id == planted.id
    assert row.status == AttendanceStatus.leave and row.note == "PM planned"
    assert row.comp_off_request_id is None


def test_a_row_written_after_the_check_is_caught_by_the_database(
    client, login, db, team, pending, monkeypatch
):
    """The race the application check cannot see: a PM's row lands between
    `_assert_off_date_free` and the write. Simulated deterministically by
    skipping the check with the row already present."""
    planted = _plant_row(db, team)
    monkeypatch.setattr(service, "_assert_off_date_free", lambda *a, **k: None)
    res = _approve(client, login, pending)
    assert res.status_code == 409, res.text
    assert "still pending" in res.json()["error"]["message"]
    assert _status(db, pending) == CompOffStatus.pending
    (row,) = _off_rows(db, team)
    assert row.id == planted.id and row.status == AttendanceStatus.present
    assert db.execute(select(AuditLog).where(
        AuditLog.action == "comp_off.request.approve")).scalar_one_or_none() is None


# -- no credit without approval -----------------------------------------------

def test_rejection_writes_no_attendance(client, login, db, team, pending):
    res = client.post(f"{API}/{pending}/reject", headers=login("pm@x.com"),
                      json={"reason": "No site work"})
    assert res.status_code == 200, res.text
    assert _off_rows(db, team) == []


def test_a_request_that_became_ineligible_cannot_be_approved(client, login, db, team, pending):
    """The PM has since ruled the worked Sunday Absent."""
    db.add(AttendanceRecord(
        employee_id=team["emp"].id, attendance_date=SUN, status=AttendanceStatus.absent,
        total_minutes=0, overtime_minutes=0,
    ))
    db.commit()
    res = _approve(client, login, pending)
    assert res.status_code == 422, res.text
    assert _status(db, pending) == CompOffStatus.pending
    assert _off_rows(db, team) == []


# -- other attendance paths -----------------------------------------------------

def test_bulk_apply_cannot_overwrite_the_day_off(client, login, db, team, pending):
    _approve(client, login, pending)
    res = client.post("/api/v1/attendance/bulk-apply", headers=login("pm@x.com"), json={
        "employee_ids": [str(team["emp"].id)], "dates": [MON.isoformat()],
        "status": "present", "dry_run": False,
    })
    assert res.status_code == 200, res.text
    result = res.json()["results"][0]
    assert result["outcome"] == "protected"
    assert result["reason_code"] == "comp_off_approval"
    (row,) = _off_rows(db, team)
    assert row.status == AttendanceStatus.comp_off


def test_ordinary_attendance_rows_carry_no_link(client, login, db, team):
    res = client.post("/api/v1/attendance", headers=login("pm@x.com"), json={
        "employee_id": str(team["emp"].id), "attendance_date": MON.isoformat(),
        "status": "comp_off",
    })
    assert res.status_code == 201, res.text
    (row,) = _off_rows(db, team)
    assert row.comp_off_request_id is None
