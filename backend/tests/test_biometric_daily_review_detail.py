"""Phase 9B - GET /biometric/daily-review/{employee_id}: the detail screen,
and the evidence/decision merge it shares with the roster view."""
from datetime import datetime, timezone

import pytest

from app.modules.biometric.models import BiometricEmployeeMapping, BiometricPunch
from app.modules.users.models import UserRole

DETAIL = "/api/v1/biometric/daily-review/{employee_id}"
REVIEW = "/api/v1/biometric/daily-review"
ATTEND = "/api/v1/attendance"
DAY = "2026-08-10"


@pytest.fixture()
def pm(auth_header):
    return auth_header("pm-detail@x.com", role=UserRole.project_manager)


def _punch(db, employee, *, code: str, hour: int, minute: int = 0, n: int = 1):
    db.add(
        BiometricPunch(
            provider="easytime",
            external_transaction_id=f"txn-{code}-{hour}-{minute}-{n}",
            external_employee_code=code,
            employee_id=None,
            punch_time=datetime(2026, 8, 10, hour, minute, tzinfo=timezone.utc),
            received_at=datetime.now(timezone.utc),
            raw_punch_state="0",
        )
    )
    db.commit()


def _map(db, employee, *, code: str):
    db.add(
        BiometricEmployeeMapping(
            provider="easytime",
            external_employee_code=code,
            employee_id=employee.id,
            is_active=True,
        )
    )
    db.commit()


def test_detail_returns_correct_employee_and_date(client, pm, db, make_employee):
    emp = make_employee(employee_code="D001", first_name="Kumar", last_name="Chandramouli")
    res = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["review_date"] == DAY
    assert body["row"]["employee_id"] == str(emp.id)
    assert body["row"]["employee_name"] == "Kumar Chandramouli"
    assert body["punches"] == []


def test_unauthorized_user_cannot_read_detail(client, auth_header, make_employee):
    emp = make_employee(employee_code="D002", first_name="A", last_name="B")
    emp_header = auth_header("emp-detail@x.com", role=UserRole.employee)
    res = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=emp_header)
    assert res.status_code == 403


def test_no_punch_official_decision_is_persisted_and_reflected(client, pm, db, make_employee):
    emp = make_employee(employee_code="D003", first_name="No", last_name="Punch")

    create = client.post(
        ATTEND,
        headers=pm,
        json={
            "employee_id": str(emp.id),
            "attendance_date": DAY,
            "status": "present",
            "check_in_at": f"{DAY}T09:10:00+05:30",
            "check_out_at": f"{DAY}T17:30:00+05:30",
            "note": "Biometric punch was missed.",
        },
    )
    assert create.status_code == 201, create.text

    detail = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm).json()
    row = detail["row"]
    # Evidence stays "no_record" - the device saw nothing.
    assert row["classification"] == "no_record"
    # But the display boundary and the decision are both visible.
    assert row["attendance_status"] == "present"
    assert row["attendance_note"] == "Biometric punch was missed."
    assert row["first_in_source"] == "pm"
    assert row["last_out_source"] == "pm"
    assert row["first_in"] is not None
    assert row["last_out"] is not None
    assert row["worked_minutes"] == 8 * 60 + 20

    roster = client.get(REVIEW, params={"date": DAY}, headers=pm).json()
    roster_row = next(r for r in roster["items"] if r["employee_id"] == str(emp.id))
    assert roster_row == row


def test_missing_out_is_completed_and_in_stays_device(client, pm, db, make_employee):
    emp = make_employee(employee_code="D004", first_name="One", last_name="Punch")
    _map(db, emp, code="D004")
    _punch(db, emp, code="D004", hour=3, minute=35)  # 09:05 IST

    before = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm).json()
    assert before["row"]["classification"] == "incomplete"
    assert before["row"]["can_set_check_in"] is False
    assert before["row"]["can_set_check_out"] is True
    assert before["row"]["first_in_source"] == "device"
    assert before["row"]["last_out_source"] is None

    update = client.post(
        ATTEND,
        headers=pm,
        json={
            "employee_id": str(emp.id),
            "attendance_date": DAY,
            "status": "present",
            "check_in_at": before["row"]["first_in"],
            "check_out_at": f"{DAY}T17:30:00+05:30",
            "note": None,
        },
    )
    assert update.status_code == 201, update.text

    after = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm).json()
    row = after["row"]
    assert row["first_in_source"] == "device"
    assert row["last_out_source"] == "pm"
    assert row["first_in"] == before["row"]["first_in"]
    assert row["last_out"] is not None
    # Evidence is still "incomplete" - only one punch was ever seen.
    assert row["classification"] == "incomplete"
    assert row["attendance_status"] == "present"


def test_two_device_punches_are_present_and_locked(client, pm, db, make_employee):
    emp = make_employee(employee_code="D005", first_name="Two", last_name="Punch")
    _map(db, emp, code="D005")
    _punch(db, emp, code="D005", hour=3, minute=48)   # 09:18 IST
    _punch(db, emp, code="D005", hour=12, minute=7)   # 17:37 IST

    detail = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm).json()
    row = detail["row"]
    assert row["classification"] == "present"
    assert row["review_required"] is False
    assert row["can_set_check_in"] is False
    assert row["can_set_check_out"] is False
    assert row["first_in_source"] == "device"
    assert row["last_out_source"] == "device"
    assert len(detail["punches"]) == 2
    assert detail["punches"][0]["role"] == "first_in"
    assert detail["punches"][1]["role"] == "last_out"
    assert all(p["source"] == "device" for p in detail["punches"])


def test_intermediate_punches_are_visible_but_not_boundaries(client, pm, db, make_employee):
    emp = make_employee(employee_code="D006", first_name="Four", last_name="Punch")
    _map(db, emp, code="D006")
    _punch(db, emp, code="D006", hour=3, minute=35)   # 09:05
    _punch(db, emp, code="D006", hour=6, minute=45)   # 12:15
    _punch(db, emp, code="D006", hour=7, minute=30)   # 13:00
    _punch(db, emp, code="D006", hour=12, minute=2)   # 17:32

    detail = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm).json()
    roles = [p["role"] for p in detail["punches"]]
    assert roles == ["first_in", "punch", "punch", "last_out"]
    assert len(detail["punches"]) == 4


def test_note_survives_reopening_and_editing(client, pm, db, make_employee):
    emp = make_employee(employee_code="D007", first_name="Note", last_name="Keeper")
    create = client.post(
        ATTEND,
        headers=pm,
        json={
            "employee_id": str(emp.id),
            "attendance_date": DAY,
            "status": "half_day",
            "check_in_at": None,
            "check_out_at": None,
            "note": "Left early - doctor appointment.",
        },
    )
    record_id = create.json()["id"]

    reopened = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm).json()
    assert reopened["row"]["attendance_note"] == "Left early - doctor appointment."

    # Editing status without resending note must not erase it.
    update = client.patch(
        f"{ATTEND}/{record_id}", headers=pm, json={"status": "present"}
    )
    assert update.status_code == 200, update.text
    assert update.json()["note"] == "Left early - doctor appointment."


def test_device_punches_are_never_modified_by_a_pm_decision(client, pm, db, make_employee):
    emp = make_employee(employee_code="D008", first_name="Immutable", last_name="Evidence")
    _map(db, emp, code="D008")
    _punch(db, emp, code="D008", hour=3, minute=35)  # 09:05, incomplete

    before_punches = sorted(
        (p.external_transaction_id, p.punch_time.isoformat())
        for p in db.query(BiometricPunch).filter_by(external_employee_code="D008").all()
    )

    client.post(
        ATTEND,
        headers=pm,
        json={
            "employee_id": str(emp.id),
            "attendance_date": DAY,
            "status": "present",
            "check_in_at": f"{DAY}T09:05:00+05:30",
            "check_out_at": f"{DAY}T17:45:00+05:30",
            "note": None,
        },
    )

    after_punches = sorted(
        (p.external_transaction_id, p.punch_time.isoformat())
        for p in db.query(BiometricPunch).filter_by(external_employee_code="D008").all()
    )
    assert before_punches == after_punches
    assert len(after_punches) == 1


def test_leave_status_flows_through_the_same_pipeline_as_present(client, pm, db, make_employee):
    """No automatic leave-request sync exists (see plan investigation summary) -
    this only proves the generic decision flow already carries `leave` through
    Records exactly like `present`, and can be revised once real evidence
    exists."""
    emp = make_employee(employee_code="D009", first_name="Leave", last_name="Day")
    create = client.post(
        ATTEND,
        headers=pm,
        json={
            "employee_id": str(emp.id),
            "attendance_date": DAY,
            "status": "leave",
            "check_in_at": None,
            "check_out_at": None,
            "note": "Approved leave.",
        },
    )
    assert create.status_code == 201, create.text
    record_id = create.json()["id"]

    detail = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm).json()
    assert detail["row"]["attendance_status"] == "leave"
    assert detail["row"]["review_required"] is False

    # The employee later punches in for real - biometric evidence appears, and
    # the PM can revise the decision through the same PATCH endpoint.
    _map(db, emp, code="D009")
    _punch(db, emp, code="D009", hour=3, minute=48)
    _punch(db, emp, code="D009", hour=12, minute=7)

    with_evidence = client.get(
        DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm
    ).json()
    assert with_evidence["row"]["classification"] == "present"
    assert with_evidence["row"]["attendance_status"] == "leave"  # still leave until PM acts

    resolved = client.patch(f"{ATTEND}/{record_id}", headers=pm, json={"status": "present"})
    assert resolved.status_code == 200, resolved.text

    final = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm).json()
    assert final["row"]["attendance_status"] == "present"
