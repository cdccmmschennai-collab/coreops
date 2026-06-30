"""API tests for the attendance module: CRUD, minute calc, RBAC, filters."""
import uuid
from datetime import date

from app.modules.attendance.models import AttendanceStatus
from app.modules.users.models import UserRole

DAY = "2026-05-01"
IN_9 = "2026-05-01T09:00:00Z"
OUT_18 = "2026-05-01T18:00:00Z"
OUT_17 = "2026-05-01T17:00:00Z"


def _payload(employee_id, **over):
    base = {
        "employee_id": str(employee_id),
        "attendance_date": DAY,
        "status": "present",
    }
    base.update(over)
    return base


# ---------- admin CRUD + calculations ----------
def test_create_computes_total_and_overtime(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    e = make_employee(employee_code="E-1")
    res = client.post(
        "/api/v1/attendance",
        headers=h,
        json=_payload(e.id, check_in_at=IN_9, check_out_at=OUT_18),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["total_minutes"] == 540
    assert body["overtime_minutes"] == 60


def test_create_without_times_is_zero(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    e = make_employee(employee_code="E-2")
    res = client.post("/api/v1/attendance", headers=h, json=_payload(e.id, status="leave"))
    assert res.status_code == 201
    assert res.json()["total_minutes"] == 0
    assert res.json()["overtime_minutes"] == 0


def test_duplicate_employee_date_409(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    e = make_employee(employee_code="E-3")
    assert client.post("/api/v1/attendance", headers=h, json=_payload(e.id)).status_code == 201
    assert client.post("/api/v1/attendance", headers=h, json=_payload(e.id)).status_code == 409


def test_create_unknown_employee_422(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    res = client.post("/api/v1/attendance", headers=h, json=_payload(uuid.uuid4()))
    assert res.status_code == 422


def test_checkout_before_checkin_422(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    e = make_employee(employee_code="E-4")
    res = client.post(
        "/api/v1/attendance",
        headers=h,
        json=_payload(e.id, check_in_at=OUT_18, check_out_at=IN_9),
    )
    assert res.status_code == 422


def test_update_recomputes_minutes(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    e = make_employee(employee_code="E-5")
    created = client.post(
        "/api/v1/attendance",
        headers=h,
        json=_payload(e.id, check_in_at=IN_9, check_out_at=OUT_18),
    ).json()
    res = client.patch(
        f"/api/v1/attendance/{created['id']}", headers=h, json={"check_out_at": OUT_17}
    )
    assert res.status_code == 200
    assert res.json()["total_minutes"] == 480
    assert res.json()["overtime_minutes"] == 0


def test_update_status(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    e = make_employee(employee_code="E-6")
    created = client.post("/api/v1/attendance", headers=h, json=_payload(e.id)).json()
    res = client.patch(
        f"/api/v1/attendance/{created['id']}", headers=h, json={"status": "absent"}
    )
    assert res.status_code == 200
    assert res.json()["status"] == "absent"


def test_delete(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    e = make_employee(employee_code="E-7")
    created = client.post("/api/v1/attendance", headers=h, json=_payload(e.id)).json()
    assert client.delete(f"/api/v1/attendance/{created['id']}", headers=h).status_code == 204
    assert client.get(f"/api/v1/attendance/{created['id']}", headers=h).status_code == 404


def test_get_unknown_404(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    assert client.get(f"/api/v1/attendance/{uuid.uuid4()}", headers=h).status_code == 404


# ---------- list / filter ----------
def test_list_pagination(client, auth_header, make_employee, make_attendance):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    e = make_employee(employee_code="E-L")
    for d in (date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3)):
        make_attendance(employee_id=e.id, attendance_date=d)
    page = client.get("/api/v1/attendance?limit=2", headers=h).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2


def test_filter_by_status(client, auth_header, make_employee, make_attendance):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    e = make_employee(employee_code="E-S")
    make_attendance(employee_id=e.id, attendance_date=date(2026, 5, 1), status=AttendanceStatus.present)
    make_attendance(employee_id=e.id, attendance_date=date(2026, 5, 2), status=AttendanceStatus.absent)
    res = client.get("/api/v1/attendance?status=absent", headers=h).json()
    assert res["total"] == 1
    assert res["items"][0]["status"] == "absent"


def test_filter_by_date_range(client, auth_header, make_employee, make_attendance):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    e = make_employee(employee_code="E-D")
    for d in (date(2026, 5, 1), date(2026, 5, 5), date(2026, 5, 10)):
        make_attendance(employee_id=e.id, attendance_date=d)
    res = client.get("/api/v1/attendance?from=2026-05-04&to=2026-05-06", headers=h).json()
    assert res["total"] == 1
    assert res["items"][0]["attendance_date"] == "2026-05-05"


# ---------- RBAC ----------
def test_viewer_reads_cannot_create(client, auth_header, make_employee, make_attendance):
    e = make_employee(employee_code="E-V")
    make_attendance(employee_id=e.id, attendance_date=date(2026, 5, 1))
    h = auth_header("viewer@example.com", role=UserRole.employee)
    assert client.get("/api/v1/attendance", headers=h).status_code == 200
    assert client.post("/api/v1/attendance", headers=h, json=_payload(e.id)).status_code == 403


def test_employee_sees_own_only(
    client, make_user, make_employee, make_attendance, login
):
    user = make_user("emp@example.com", role=UserRole.employee)
    me = make_employee(employee_code="MINE", user_id=user.id)
    other = make_employee(employee_code="OTHER")
    make_attendance(employee_id=me.id, attendance_date=date(2026, 5, 1))
    make_attendance(employee_id=other.id, attendance_date=date(2026, 5, 1))
    h = login("emp@example.com")
    res = client.get("/api/v1/attendance", headers=h).json()
    assert res["total"] == 1
    assert res["items"][0]["employee_id"] == str(me.id)


def test_employee_get_other_403(
    client, make_user, make_employee, make_attendance, login
):
    user = make_user("emp@example.com", role=UserRole.employee)
    make_employee(employee_code="MINE", user_id=user.id)
    other = make_employee(employee_code="OTHER")
    rec = make_attendance(employee_id=other.id, attendance_date=date(2026, 5, 1))
    h = login("emp@example.com")
    assert client.get(f"/api/v1/attendance/{rec.id}", headers=h).status_code == 403


def test_project_manager_sees_all_and_can_create(
    client, make_user, make_employee, make_attendance, login
):
    user = make_user("mgr@example.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MGR", user_id=user.id)
    report = make_employee(employee_code="R1", manager_id=mgr.id)
    outsider = make_employee(employee_code="X1")
    make_attendance(employee_id=report.id, attendance_date=date(2026, 5, 1))
    make_attendance(employee_id=outsider.id, attendance_date=date(2026, 5, 1))
    h = login("mgr@example.com")
    res = client.get("/api/v1/attendance", headers=h).json()
    # project_manager sees ALL attendance records (no team scoping)
    assert res["total"] == 2
    # project_manager can create attendance records (use a different date to avoid duplicate)
    new_record = _payload(report.id, **{"attendance_date": "2026-05-02"})
    assert client.post("/api/v1/attendance", headers=h, json=new_record).status_code == 201


def test_employee_attendance_endpoint_scoped(
    client, make_user, make_employee, make_attendance, login, auth_header
):
    user = make_user("emp@example.com", role=UserRole.employee)
    me = make_employee(employee_code="MINE", user_id=user.id)
    other = make_employee(employee_code="OTHER")
    make_attendance(employee_id=me.id, attendance_date=date(2026, 5, 1))
    make_attendance(employee_id=other.id, attendance_date=date(2026, 5, 1))
    h = login("emp@example.com")
    assert client.get(f"/api/v1/employees/{me.id}/attendance", headers=h).status_code == 200
    assert client.get(f"/api/v1/employees/{other.id}/attendance", headers=h).status_code == 403
    admin = auth_header("admin@example.com", role=UserRole.project_manager)
    assert client.get(f"/api/v1/employees/{other.id}/attendance", headers=admin).status_code == 200


# ---------- bulk: GET sheet ----------
def test_sheet_no_attendance_defaults_present(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    e1 = make_employee(employee_code="S-1", first_name="John")
    e2 = make_employee(employee_code="S-2", first_name="David")
    res = client.get(f"/api/v1/attendance/sheet?date={DAY}", headers=h)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["attendance_date"] == DAY
    assert body["exists"] is False
    by_id = {r["employee_id"]: r for r in body["rows"]}
    assert by_id[str(e1.id)]["status"] == "present"
    assert by_id[str(e2.id)]["status"] == "present"
    # Rows carry display fields the grid needs.
    assert by_id[str(e1.id)]["employee_code"] == "S-1"
    assert "employee_name" in by_id[str(e1.id)]


def test_sheet_merges_saved_records(client, auth_header, make_employee, make_attendance):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    saved = make_employee(employee_code="S-3")
    fresh = make_employee(employee_code="S-4")
    make_attendance(
        employee_id=saved.id, attendance_date=date(2026, 5, 1), status=AttendanceStatus.absent
    )
    body = client.get(f"/api/v1/attendance/sheet?date={DAY}", headers=h).json()
    assert body["exists"] is True
    by_id = {r["employee_id"]: r for r in body["rows"]}
    assert by_id[str(saved.id)]["status"] == "absent"
    # Employee with no record for the date still defaults to present.
    assert by_id[str(fresh.id)]["status"] == "present"


def test_sheet_excludes_deleted_employees(client, auth_header, make_employee, db):
    from datetime import datetime, timezone

    h = auth_header("admin@example.com", role=UserRole.project_manager)
    active = make_employee(employee_code="S-A")
    gone = make_employee(employee_code="S-G")
    gone.deleted_at = datetime.now(timezone.utc)
    db.commit()
    body = client.get(f"/api/v1/attendance/sheet?date={DAY}", headers=h).json()
    ids = {r["employee_id"] for r in body["rows"]}
    assert str(active.id) in ids
    assert str(gone.id) not in ids


def test_sheet_requires_project_manager(client, auth_header, make_employee):
    make_employee(employee_code="S-R")
    h = auth_header("emp@example.com", role=UserRole.employee)
    assert client.get(f"/api/v1/attendance/sheet?date={DAY}", headers=h).status_code == 403


# ---------- bulk: POST save ----------
def _bulk(records, day=DAY):
    return {"date": day, "records": records}


def test_bulk_creates_records(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    e1 = make_employee(employee_code="B-1")
    e2 = make_employee(employee_code="B-2")
    body = _bulk(
        [
            {"employee_id": str(e1.id), "status": "present"},
            {"employee_id": str(e2.id), "status": "absent"},
        ]
    )
    res = client.post("/api/v1/attendance/bulk", headers=h, json=body)
    assert res.status_code == 200, res.text
    page = client.get("/api/v1/attendance", headers=h).json()
    assert page["total"] == 2
    by_id = {r["employee_id"]: r for r in client.get(f"/api/v1/attendance/sheet?date={DAY}", headers=h).json()["rows"]}
    assert by_id[str(e1.id)]["status"] == "present"
    assert by_id[str(e2.id)]["status"] == "absent"


def test_bulk_updates_without_duplicates(client, auth_header, make_employee, make_attendance):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    e = make_employee(employee_code="B-3")
    make_attendance(
        employee_id=e.id, attendance_date=date(2026, 5, 1), status=AttendanceStatus.present
    )
    res = client.post(
        "/api/v1/attendance/bulk",
        headers=h,
        json=_bulk([{"employee_id": str(e.id), "status": "leave"}]),
    )
    assert res.status_code == 200, res.text
    page = client.get("/api/v1/attendance", headers=h).json()
    # Upsert: still one row for the (employee, date), not a duplicate.
    assert page["total"] == 1
    assert page["items"][0]["status"] == "leave"


def test_bulk_unknown_employee_422_no_partial_save(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    e = make_employee(employee_code="B-4")
    res = client.post(
        "/api/v1/attendance/bulk",
        headers=h,
        json=_bulk(
            [
                {"employee_id": str(e.id), "status": "present"},
                {"employee_id": str(uuid.uuid4()), "status": "absent"},
            ]
        ),
    )
    assert res.status_code == 422
    # Whole batch rolled back — the valid record must NOT have been created.
    assert client.get("/api/v1/attendance", headers=h).json()["total"] == 0


def test_bulk_requires_project_manager(client, auth_header, make_employee):
    e = make_employee(employee_code="B-5")
    h = auth_header("emp@example.com", role=UserRole.employee)
    res = client.post(
        "/api/v1/attendance/bulk",
        headers=h,
        json=_bulk([{"employee_id": str(e.id), "status": "present"}]),
    )
    assert res.status_code == 403
