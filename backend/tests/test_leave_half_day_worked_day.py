"""Half-day leave on a day the employee also punched (Phase 1).

A half-day leave is taken on a day the employee attends for the other half, so
a settled-present biometric day is the expected evidence for it, not a
contradiction. The biometric guard therefore applies to full-day leave only;
`test_leave_biometric_block.py` keeps proving the full-day refusal.

Phase 2: a day already recorded Present no longer refuses a half-day leave
either. Approval converts that row in place to `half_day` + 0.5 (times kept), and
cancelling the leave restores it to Present with its note. The conversion is
tracked by its audit entry, so PM edits to the day cannot break the restore. A
day recorded `half_day` still refuses, and full-day leave is still refused on any
worked day.

    docker exec wms-backend-1 pytest tests/test_leave_half_day_worked_day.py
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.audit.models import AuditLog
from app.modules.biometric.models import BiometricEmployeeMapping, BiometricPunch
from app.modules.leave.models import LeaveRequest, LeaveStatus
from app.modules.leave_balances import ledger
from app.modules.users.models import UserRole

API = "/api/v1/leave-requests"

IST = timezone(timedelta(hours=5, minutes=30))

# 2027-03-08 is a Monday - an ordinary working day.
MON = date(2027, 3, 8)

CODE = "9001"


@pytest.fixture()
def team(db, make_user, make_employee):
    mu = make_user("mgr@x.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MGR", user_id=mu.id)
    eu = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="EMP069", user_id=eu.id, manager_id=mgr.id)
    db.add(
        BiometricEmployeeMapping(
            provider="easytime",
            external_employee_code=CODE,
            employee_id=emp.id,
            is_active=True,
        )
    )
    db.commit()
    return {"manager": mgr, "employee": emp}


def _punch_full_day(db, day: date) -> None:
    for n, (hh, mm) in enumerate(((9, 10), (17, 54))):
        db.add(
            BiometricPunch(
                provider="easytime",
                external_transaction_id=f"txn-{day}-{n}",
                external_employee_code=CODE,
                employee_id=None,
                punch_time=datetime(day.year, day.month, day.day, hh, mm, tzinfo=IST),
                received_at=datetime.now(timezone.utc),
                raw_punch_state="0",
            )
        )
    db.commit()


def _file_half(client, login, day: date = MON, period: str = "second_half"):
    return client.post(
        API,
        headers=login("emp@x.com"),
        json={
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
            "half_day_period": period,
            "reason": "Doctor visit",
        },
    )


def test_half_day_can_be_requested_on_a_fully_punched_day(client, login, db, team):
    _punch_full_day(db, MON)
    res = _file_half(client, login)
    assert res.status_code == 201, res.text
    assert res.json()["half_day_period"] == "second_half"


def test_half_day_request_on_a_punched_day_can_be_edited(client, login, db, team):
    _punch_full_day(db, MON)
    created = _file_half(client, login)
    assert created.status_code == 201, created.text
    res = client.patch(
        f"{API}/{created.json()['id']}",
        headers=login("emp@x.com"),
        json={"start_date": MON.isoformat(), "end_date": MON.isoformat(),
              "reason": "Doctor visit (moved)"},
    )
    assert res.status_code == 200, res.text


def test_half_day_on_a_punched_day_approves_and_charges_half(client, login, db, team):
    """Punches may arrive before or after filing; either way the approval goes
    through, writes the half-day row, and leaves every punch where it was."""
    created = _file_half(client, login)
    assert created.status_code == 201, created.text
    _punch_full_day(db, MON)  # synced after filing, before approval

    res = client.post(
        f"{API}/{created.json()['id']}/approve", headers=login("mgr@x.com"), json={}
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"

    record = db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.employee_id == team["employee"].id,
            AttendanceRecord.attendance_date == MON,
        )
    ).scalar_one()
    assert record.status == AttendanceStatus.half_day
    assert record.leave_day_fraction == Decimal("0.5")
    punches = db.execute(
        select(func.count()).select_from(BiometricPunch).where(
            BiometricPunch.external_employee_code == CODE
        )
    ).scalar_one()
    assert punches == 2


def test_full_day_leave_is_still_refused_on_a_punched_day(client, login, db, team):
    _punch_full_day(db, MON)
    res = client.post(
        API,
        headers=login("emp@x.com"),
        json={"start_date": MON.isoformat(), "end_date": MON.isoformat()},
    )
    assert res.status_code == 422, res.text
    assert "biometric record" in res.json()["error"]["message"]


def _attendance_today_is_mon(monkeypatch) -> None:
    """For the cases where a PM edits the converted day afterwards. The
    attendance PATCH refuses times on a future day, and a past leave cannot be
    cancelled - so the attendance calendar alone is told MON is today."""
    from app.modules.attendance import service as attendance_service

    monkeypatch.setattr(attendance_service, "_business_today", lambda: MON)


ORIGINAL_NOTE = "Marked from the sheet"


def _in(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 9, 10, tzinfo=IST)


def _out(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 17, 54, tzinfo=IST)


def _record(
    db, team, status: AttendanceStatus, day: date = MON, *, times: bool = True,
    note: str | None = None,
) -> AttendanceRecord:
    record = AttendanceRecord(
        employee_id=team["employee"].id,
        attendance_date=day,
        status=status,
        check_in_at=_in(day) if times else None,
        check_out_at=_out(day) if times else None,
        total_minutes=524 if times else 0,
        overtime_minutes=0,
        note=note,
    )
    db.add(record)
    db.commit()
    return record


def _day_row(db, team, day: date = MON) -> AttendanceRecord | None:
    db.expire_all()
    return db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.employee_id == team["employee"].id,
            AttendanceRecord.attendance_date == day,
        )
    ).scalar_one_or_none()


def _approve(client, login, req_id) -> None:
    res = client.post(f"{API}/{req_id}/approve", headers=login("mgr@x.com"), json={})
    assert res.status_code == 200, res.text


def _cancel(client, login, req_id, decision: str = "approve-cancellation") -> None:
    res = client.post(f"{API}/{req_id}/request-cancellation", headers=login("emp@x.com"))
    assert res.status_code == 200, res.text
    res = client.post(f"{API}/{req_id}/{decision}", headers=login("mgr@x.com"))
    assert res.status_code == 200, res.text


def _converted_and_approved(client, login, db, team, day: date = MON, **record):
    _record(db, team, AttendanceStatus.present, day, note=ORIGINAL_NOTE, **record)
    created = _file_half(client, login, day)
    assert created.status_code == 201, created.text
    req_id = created.json()["id"]
    _approve(client, login, req_id)
    return req_id


def _attendance_audits(db, record_id, source: str) -> list[dict]:
    db.expire_all()
    return [
        a.details
        for a in db.execute(
            select(AuditLog)
            .where(AuditLog.entity_id == record_id)
            .order_by(AuditLog.created_at)
        ).scalars()
        if a.details.get("source") == source
    ]


@pytest.mark.parametrize("period", ["first_half", "second_half"])
def test_half_day_on_a_recorded_present_day_converts_the_row(
    client, login, db, team, period
):
    """A recorded Present day no longer refuses a half-day leave, for either
    half. The approval turns that same row into the half-day row, keeping its
    exact times."""
    original = _record(db, team, AttendanceStatus.present, note=ORIGINAL_NOTE)
    created = _file_half(client, login, period=period)
    assert created.status_code == 201, created.text
    _approve(client, login, created.json()["id"])

    row = _day_row(db, team)
    assert row.id == original.id
    assert row.status == AttendanceStatus.half_day
    assert row.leave_day_fraction == Decimal("0.5")
    assert row.check_in_at == _in(MON) and row.check_out_at == _out(MON)
    assert row.total_minutes == 524
    assert db.execute(
        select(func.count()).select_from(AttendanceRecord).where(
            AttendanceRecord.employee_id == team["employee"].id
        )
    ).scalar_one() == 1


def test_cancelling_a_converted_half_day_restores_present_and_its_note(
    client, login, db, team, make_leave_adjustment
):
    """Approval charges exactly 0.5; cancellation gives the day back as it was -
    Present, its own times and note - and refunds the 0.5."""
    make_leave_adjustment(
        employee_id=team["employee"].id, effective_month=date(2027, 3, 1), days="3"
    )

    def balance():
        db.expire_all()
        return ledger.closing_balance(db, team["employee"].id, date(2027, 3, 1))

    assert balance() == Decimal("3.00")
    req_id = _converted_and_approved(client, login, db, team)
    assert balance() == Decimal("2.50")

    _cancel(client, login, req_id)
    row = _day_row(db, team)
    assert row.status == AttendanceStatus.present
    assert row.leave_day_fraction is None
    assert row.note == ORIGINAL_NOTE
    assert row.check_in_at == _in(MON) and row.check_out_at == _out(MON)
    assert balance() == Decimal("3.00")


def test_a_converted_day_without_times_is_restored_not_deleted(
    client, login, db, team
):
    """A Present row with no times converts to a row shaped exactly like a fresh
    half-day approval row. The cancellation must still restore it - it was a
    worked day - rather than delete it as the approval's own row."""
    req_id = _converted_and_approved(client, login, db, team, times=False)
    _cancel(client, login, req_id)

    row = _day_row(db, team)
    assert row is not None
    assert row.status == AttendanceStatus.present
    assert row.note == ORIGINAL_NOTE


def test_editing_the_note_after_approval_does_not_break_cancellation(
    client, login, db, team, monkeypatch
):
    _attendance_today_is_mon(monkeypatch)
    req_id = _converted_and_approved(client, login, db, team)
    row = _day_row(db, team)
    res = client.patch(
        f"/api/v1/attendance/{row.id}",
        headers=login("mgr@x.com"),
        json={"note": "PM remark"},
    )
    assert res.status_code == 200, res.text

    _cancel(client, login, req_id)
    row = _day_row(db, team)
    assert row.status == AttendanceStatus.present
    assert row.leave_day_fraction is None
    # A later PM reason is not overwritten by the original.
    assert row.note == "PM remark"


def test_a_time_correction_after_approval_survives_the_restore(
    client, login, db, team, monkeypatch
):
    _attendance_today_is_mon(monkeypatch)
    req_id = _converted_and_approved(client, login, db, team)
    row = _day_row(db, team)
    corrected = datetime(MON.year, MON.month, MON.day, 9, 40, tzinfo=IST)
    res = client.patch(
        f"/api/v1/attendance/{row.id}",
        headers=login("mgr@x.com"),
        json={"check_in_at": corrected.isoformat(), "note": "Late badge"},
    )
    assert res.status_code == 200, res.text

    _cancel(client, login, req_id)
    row = _day_row(db, team)
    assert row.status == AttendanceStatus.present
    assert row.check_in_at == corrected
    assert row.check_out_at == _out(MON)


def test_a_converted_day_a_pm_moved_off_half_day_is_left_alone(
    client, login, db, team, monkeypatch
):
    _attendance_today_is_mon(monkeypatch)
    req_id = _converted_and_approved(client, login, db, team)
    row = _day_row(db, team)
    res = client.patch(
        f"/api/v1/attendance/{row.id}",
        headers=login("mgr@x.com"),
        json={"status": "absent", "note": "Did not attend after all"},
    )
    assert res.status_code == 200, res.text

    _cancel(client, login, req_id)
    row = _day_row(db, team)
    assert row is not None
    assert row.status == AttendanceStatus.absent


def test_rejected_cancellation_keeps_the_conversion(client, login, db, team):
    req_id = _converted_and_approved(client, login, db, team)
    _cancel(client, login, req_id, "reject-cancellation")

    row = _day_row(db, team)
    assert row.status == AttendanceStatus.half_day
    assert row.leave_day_fraction == Decimal("0.5")


def test_rejecting_a_pending_half_day_leaves_present_untouched(
    client, login, db, team
):
    _record(db, team, AttendanceStatus.present, note=ORIGINAL_NOTE)
    req_id = _file_half(client, login).json()["id"]
    res = client.post(f"{API}/{req_id}/reject", headers=login("mgr@x.com"), json={})
    assert res.status_code == 200, res.text

    row = _day_row(db, team)
    assert row.status == AttendanceStatus.present
    assert row.leave_day_fraction is None
    assert row.note == ORIGINAL_NOTE
    assert row.check_in_at == _in(MON)


def test_bulk_apply_cannot_overwrite_a_converted_day(client, login, db, team):
    req_id = _converted_and_approved(client, login, db, team)
    res = client.post(
        "/api/v1/attendance/bulk-apply",
        headers=login("mgr@x.com"),
        json={
            "employee_ids": [str(team["employee"].id)],
            "dates": [MON.isoformat()],
            "status": "present",
            "dry_run": False,
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["results"][0]["outcome"] == "protected"
    assert _day_row(db, team).status == AttendanceStatus.half_day

    # Once the leave is cancelled the day is an ordinary record again.
    _cancel(client, login, req_id)
    res = client.post(
        "/api/v1/attendance/bulk-apply",
        headers=login("mgr@x.com"),
        json={
            "employee_ids": [str(team["employee"].id)],
            "dates": [MON.isoformat()],
            "status": "absent",
            "dry_run": False,
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["results"][0]["outcome"] == "updated"


def test_conversion_and_restore_are_audited_in_full(client, login, db, team):
    req_id = _converted_and_approved(client, login, db, team)
    record_id = _day_row(db, team).id

    (approval,) = _attendance_audits(db, record_id, "leave_approval")
    assert approval["previous_status"] == "present"
    assert approval["status"] == "half_day"
    assert approval["previous_leave_day_fraction"] is None
    assert approval["leave_day_fraction"] == 0.5
    assert approval["previous_note"] == ORIGINAL_NOTE
    assert approval["leave_request_id"] == req_id
    assert approval["half_day_period"] == "second_half"

    _cancel(client, login, req_id)
    (restore,) = _attendance_audits(db, record_id, "leave_cancellation")
    assert restore["previous_status"] == "half_day"
    assert restore["status"] == "present"
    assert restore["previous_leave_day_fraction"] == 0.5
    assert restore["leave_day_fraction"] is None
    assert restore["note"] == ORIGINAL_NOTE
    assert restore["leave_request_id"] == req_id


def test_a_recorded_half_day_still_refuses_half_day_leave(client, login, db, team):
    _record(db, team, AttendanceStatus.half_day)
    res = _file_half(client, login)
    assert res.status_code == 422, res.text
    assert "marked present" in res.json()["error"]["message"]
    assert db.execute(
        select(func.count()).select_from(LeaveRequest).where(
            LeaveRequest.employee_id == team["employee"].id,
            LeaveRequest.status == LeaveStatus.pending,
        )
    ).scalar_one() == 0


def test_full_day_leave_is_still_refused_on_a_recorded_present_day(
    client, login, db, team
):
    _record(db, team, AttendanceStatus.present)
    res = client.post(
        API,
        headers=login("emp@x.com"),
        json={"start_date": MON.isoformat(), "end_date": MON.isoformat()},
    )
    assert res.status_code == 422, res.text
    assert "marked present" in res.json()["error"]["message"]
