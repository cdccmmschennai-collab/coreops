"""Full-Day / Split-Day work report periods (migration 0060).

Covers the approved matrix: legacy payload compatibility (one Full-Day period
always maintained), the split-day service invariants, server-derived fractions
+ submit-time base/fraction/effective snapshots, per-period activity routing of
approved activity requests, the fraction-aware live benchmark ledger,
compliance fractions (warn-only), and the feature-flag OFF behaviour.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.modules.activity_master.service import get_daily_benchmark_ledger
from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole
from app.modules.work_reports.models import WorkReportPeriod, WorkReportTask

BASE = "/api/v1/work-reports"
TODAY = date.today().isoformat()


@pytest.fixture()
def day_parts_on():
    prev = settings.REPORT_DAY_PARTS_ENABLED
    settings.REPORT_DAY_PARTS_ENABLED = True
    try:
        yield
    finally:
        settings.REPORT_DAY_PARTS_ENABLED = prev


@pytest.fixture()
def setup_author(make_user, make_employee, make_project, make_project_member, login):
    def _make(*, email="emp@x.com", code="E-1", proj_code="P-1"):
        u = make_user(email, role=UserRole.employee)
        e = make_employee(employee_code=code, user_id=u.id)
        p = make_project(code=proj_code, status=ProjectStatus.active)
        make_project_member(project_id=p.id, employee_id=e.id)
        return {"user": u, "emp": e, "project": p, "header": login(email)}

    return _make


@pytest.fixture()
def pm_header(auth_header):
    return auth_header(email="pm@x.com", role=UserRole.project_manager)


def _make_sub_activity(
    client, admin_header, *, benchmark_type=None, benchmark_value=None,
    relevant_count_field=None, name="Sub", period_days=None,
):
    a = client.post(
        "/api/v1/activity-master/activities",
        json={"name": f"Activity for {name}"}, headers=admin_header,
    ).json()
    body = {"name": name}
    if benchmark_type:
        body["benchmark_type"] = benchmark_type
    if benchmark_value is not None:
        body["benchmark_value"] = benchmark_value
    if relevant_count_field is not None:
        body["relevant_count_field"] = relevant_count_field
    sub = client.post(
        f"/api/v1/activity-master/activities/{a['id']}/sub-activities",
        json=body, headers=admin_header,
    ).json()
    if period_days is not None:
        res = client.patch(
            f"/api/v1/activity-master/sub-activities/{sub['id']}",
            json={"benchmark_period_days": period_days}, headers=admin_header,
        )
        assert res.status_code == 200, res.text
    return a, sub


def _task(project_id, sub_id=None, **counts):
    body = {"project_id": str(project_id), "description": "work"}
    if sub_id:
        body["sub_activity_id"] = sub_id
    body.update(counts)
    return body


def _split_payload(first, second, report_date=TODAY):
    return {
        "report_date": report_date,
        "report_mode": "split_day",
        "periods": [
            {"day_part": "first_half", **first},
            {"day_part": "second_half", **second},
        ],
    }


# ── legacy payload compatibility ────────────────────────────────────────────

def test_legacy_payload_creates_full_day_period(client, setup_author):
    a = setup_author()
    payload = {
        "report_date": TODAY, "day_status": "work_at_office",
        "location": "chennai",
        "tasks": [_task(a["project"].id)],
    }
    created = client.post(BASE, headers=a["header"], json=payload).json()
    assert created["report_mode"] == "full_day"
    assert len(created["periods"]) == 1
    p = created["periods"][0]
    assert p["day_part"] == "full_day"
    assert p["period_status"] == "work_at_office"
    assert p["location"] == "chennai"
    assert float(p["work_fraction"]) == 1.0
    assert p["is_legacy_half_day"] is False
    assert len(p["tasks"]) == 1
    # The flat task list keeps working and carries the period link.
    assert created["tasks"][0]["period_id"] == p["id"]
    assert created["tasks"][0]["day_part"] == "full_day"


def test_legacy_leave_report_has_empty_full_day_period(client, setup_author):
    a = setup_author()
    payload = {"report_date": TODAY, "day_status": "leave", "tasks": []}
    created = client.post(BASE, headers=a["header"], json=payload).json()
    assert created["report_mode"] == "full_day"
    assert created["periods"][0]["period_status"] == "leave"
    assert created["periods"][0]["tasks"] == []
    # Submits fine — a leave day owes no activities.
    res = client.post(f"{BASE}/{created['id']}/submit", headers=a["header"])
    assert res.status_code == 200, res.text


def test_legacy_half_day_freezes_half_benchmark_with_base_and_fraction(
    client, setup_author, pm_header
):
    a = setup_author()
    _, sub = _make_sub_activity(
        client, pm_header, benchmark_type="NUMERIC", benchmark_value=120,
        relevant_count_field="tags", name="HALF-DAY-SUB",
    )
    payload = {
        "report_date": TODAY, "day_status": "half_day", "location": "chennai",
        "tasks": [_task(a["project"].id, sub["id"], tags_count=50)],
    }
    created = client.post(BASE, headers=a["header"], json=payload).json()
    p = created["periods"][0]
    assert float(p["work_fraction"]) == 0.5
    assert p["is_legacy_half_day"] is True

    submitted = client.post(f"{BASE}/{created['id']}/submit", headers=a["header"]).json()
    task = submitted["tasks"][0]
    assert float(task["benchmark_base_value_snapshot"]) == 120.0
    assert float(task["benchmark_fraction_snapshot"]) == 0.5
    assert float(task["benchmark_value_snapshot"]) == 60.0   # effective
    assert float(task["deficit"]) == 10.0                     # 60 - 50
    assert round(float(task["productivity_pct"]), 2) == 83.33


def test_legacy_update_resyncs_period_and_relinks_tasks(client, setup_author):
    a = setup_author()
    created = client.post(BASE, headers=a["header"], json={
        "report_date": TODAY, "day_status": "work_at_office", "location": "chennai",
        "tasks": [_task(a["project"].id)],
    }).json()
    updated = client.patch(f"{BASE}/{created['id']}", headers=a["header"], json={
        "day_status": "half_day",
        "tasks": [_task(a["project"].id)],
    }).json()
    p = updated["periods"][0]
    assert float(p["work_fraction"]) == 0.5
    assert p["is_legacy_half_day"] is True
    assert updated["tasks"][0]["period_id"] == p["id"]


# ── feature flag ────────────────────────────────────────────────────────────

def test_split_payload_rejected_when_flag_off(client, setup_author):
    a = setup_author()
    payload = _split_payload(
        {"period_status": "leave"},
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id)]},
    )
    res = client.post(BASE, headers=a["header"], json=payload)
    assert res.status_code == 422
    assert "not enabled" in res.json()["error"]["message"]


# ── split-day invariants ────────────────────────────────────────────────────

def test_split_leave_then_work(client, setup_author, pm_header, day_parts_on):
    a = setup_author()
    _, sub = _make_sub_activity(
        client, pm_header, benchmark_type="NUMERIC", benchmark_value=120,
        relevant_count_field="pages", name="SPLIT-PAGES",
    )
    payload = _split_payload(
        {"period_status": "leave", "remarks": "half-day leave"},
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id, sub["id"], pages_count=50)]},
    )
    created = client.post(BASE, headers=a["header"], json=payload).json()
    assert created["report_mode"] == "split_day"
    # Derived header: one working half -> the legacy 'half_day' day status,
    # located where the working half was.
    assert created["day_status"] == "half_day"
    assert created["location"] == "chennai"
    parts = {p["day_part"]: p for p in created["periods"]}
    assert set(parts) == {"first_half", "second_half"}
    assert float(parts["first_half"]["work_fraction"]) == 0.5
    assert parts["first_half"]["tasks"] == []
    assert parts["first_half"]["remarks"] == "half-day leave"
    assert len(parts["second_half"]["tasks"]) == 1

    submitted = client.post(f"{BASE}/{created['id']}/submit", headers=a["header"]).json()
    task = submitted["tasks"][0]
    assert task["day_part"] == "second_half"
    assert float(task["benchmark_base_value_snapshot"]) == 120.0
    assert float(task["benchmark_fraction_snapshot"]) == 0.5
    assert float(task["benchmark_value_snapshot"]) == 60.0
    assert float(task["deficit"]) == 10.0


def test_split_work_then_leave(client, setup_author, pm_header, day_parts_on):
    a = setup_author()
    _, sub = _make_sub_activity(
        client, pm_header, benchmark_type="NUMERIC", benchmark_value=100,
        relevant_count_field="docs", name="SPLIT-DOCS",
    )
    payload = _split_payload(
        {"period_status": "work_from_home", "location": "hyderabad",
         "tasks": [_task(a["project"].id, sub["id"], docs_count=50)]},
        {"period_status": "comp_off"},
    )
    created = client.post(BASE, headers=a["header"], json=payload).json()
    assert created["day_status"] == "half_day"
    assert created["location"] == "hyderabad"
    submitted = client.post(f"{BASE}/{created['id']}/submit", headers=a["header"]).json()
    assert float(submitted["tasks"][0]["benchmark_value_snapshot"]) == 50.0
    assert float(submitted["tasks"][0]["deficit"]) == 0.0


def test_split_two_working_halves_different_activities(
    client, setup_author, pm_header, day_parts_on
):
    a = setup_author()
    _, sub1 = _make_sub_activity(
        client, pm_header, benchmark_type="NUMERIC", benchmark_value=120,
        relevant_count_field="tags", name="AM-TAGS",
    )
    _, sub2 = _make_sub_activity(
        client, pm_header, benchmark_type="NUMERIC", benchmark_value=80,
        relevant_count_field="docs", name="PM-DOCS",
    )
    payload = _split_payload(
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id, sub1["id"], tags_count=60)]},
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id, sub2["id"], docs_count=40)]},
    )
    created = client.post(BASE, headers=a["header"], json=payload).json()
    # Both halves working -> header keeps the first half's working status.
    assert created["day_status"] == "work_at_office"
    submitted = client.post(f"{BASE}/{created['id']}/submit", headers=a["header"]).json()
    by_part = {t["day_part"]: t for t in submitted["tasks"]}
    assert float(by_part["first_half"]["benchmark_value_snapshot"]) == 60.0
    assert float(by_part["second_half"]["benchmark_value_snapshot"]) == 40.0
    assert float(by_part["first_half"]["deficit"]) == 0.0
    assert float(by_part["second_half"]["deficit"]) == 0.0


def test_split_same_activity_both_halves_keeps_rows_and_aggregates_ledger(
    client, db, setup_author, pm_header, day_parts_on
):
    a = setup_author()
    _, sub = _make_sub_activity(
        client, pm_header, benchmark_type="NUMERIC", benchmark_value=120,
        relevant_count_field="tags", name="SAME-BOTH",
    )
    payload = _split_payload(
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id, sub["id"], tags_count=40)]},
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id, sub["id"], tags_count=50)]},
    )
    created = client.post(BASE, headers=a["header"], json=payload).json()
    client.post(f"{BASE}/{created['id']}/submit", headers=a["header"])

    # Separate task rows are retained…
    rows = db.execute(
        select(WorkReportTask).where(WorkReportTask.report_id == created["id"])
    ).scalars().all()
    assert len(rows) == 2
    # …and each is frozen at half the base.
    assert sorted(float(r.benchmark_value_snapshot) for r in rows) == [60.0, 60.0]

    # The live ledger aggregates: one (employee, date, sub) row with the FULL
    # base target (0.5 + 0.5 capped at 1.0) and the summed actual.
    ledger = get_daily_benchmark_ledger(db, employee_ids={a["emp"].id})
    assert len(ledger) == 1
    assert float(ledger[0]["target"]) == 120.0
    assert float(ledger[0]["actual"]) == 90.0


def test_ledger_halves_target_for_single_working_half(
    client, db, setup_author, pm_header, day_parts_on
):
    a = setup_author()
    _, sub = _make_sub_activity(
        client, pm_header, benchmark_type="NUMERIC", benchmark_value=120,
        relevant_count_field="tags", name="LEDGER-HALF",
    )
    payload = _split_payload(
        {"period_status": "leave"},
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id, sub["id"], tags_count=50)]},
    )
    created = client.post(BASE, headers=a["header"], json=payload).json()
    client.post(f"{BASE}/{created['id']}/submit", headers=a["header"])
    ledger = get_daily_benchmark_ledger(db, employee_ids={a["emp"].id})
    assert len(ledger) == 1
    assert float(ledger[0]["target"]) == 60.0
    assert float(ledger[0]["pending"]) == 10.0


def test_split_both_halves_nonworking_rejected(client, setup_author, day_parts_on):
    a = setup_author()
    payload = _split_payload(
        {"period_status": "leave"}, {"period_status": "week_off"},
    )
    res = client.post(BASE, headers=a["header"], json=payload)
    assert res.status_code == 422
    assert "Full Day" in res.json()["error"]["message"]


def test_split_duplicate_or_mixed_parts_rejected(client, setup_author, day_parts_on):
    a = setup_author()
    dup = {
        "report_date": TODAY, "report_mode": "split_day",
        "periods": [
            {"day_part": "first_half", "period_status": "leave"},
            {"day_part": "first_half", "period_status": "work_at_office",
             "tasks": [_task(a["project"].id)]},
        ],
    }
    assert client.post(BASE, headers=a["header"], json=dup).status_code == 422
    mixed = {
        "report_date": TODAY,
        "periods": [
            {"day_part": "full_day", "period_status": "work_at_office",
             "tasks": [_task(a["project"].id)]},
            {"day_part": "second_half", "period_status": "leave"},
        ],
    }
    assert client.post(BASE, headers=a["header"], json=mixed).status_code == 422


def test_half_day_status_invalid_for_half_period(client, setup_author, day_parts_on):
    a = setup_author()
    payload = _split_payload(
        {"period_status": "half_day",
         "tasks": [_task(a["project"].id)]},
        {"period_status": "leave"},
    )
    res = client.post(BASE, headers=a["header"], json=payload)
    assert res.status_code == 422


def test_nonworking_period_drops_tasks(client, setup_author, day_parts_on):
    a = setup_author()
    payload = _split_payload(
        {"period_status": "leave", "tasks": [_task(a["project"].id)]},
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id)]},
    )
    created = client.post(BASE, headers=a["header"], json=payload).json()
    parts = {p["day_part"]: p for p in created["periods"]}
    assert parts["first_half"]["tasks"] == []
    assert len(created["tasks"]) == 1


def test_submit_requires_activity_in_every_working_period(
    client, setup_author, day_parts_on
):
    a = setup_author()
    payload = _split_payload(
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id)]},
        {"period_status": "work_at_office", "location": "chennai", "tasks": []},
    )
    created = client.post(BASE, headers=a["header"], json=payload).json()
    res = client.post(f"{BASE}/{created['id']}/submit", headers=a["header"])
    assert res.status_code == 422
    assert "Second Half" in res.json()["error"]["message"]


def test_client_cannot_supply_work_fraction(client, db, setup_author, day_parts_on):
    a = setup_author()
    payload = _split_payload(
        {"period_status": "leave"},
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id)]},
    )
    # A spoofed fraction on both periods must be ignored (unknown field).
    for p in payload["periods"]:
        p["work_fraction"] = 1.0
    created = client.post(BASE, headers=a["header"], json=payload).json()
    fractions = sorted(
        float(p.work_fraction) for p in db.execute(
            select(WorkReportPeriod).where(
                WorkReportPeriod.report_id == created["id"]
            )
        ).scalars()
    )
    assert fractions == [0.5, 0.5]


def test_task_based_deadline_unscaled_in_half_period(
    client, setup_author, pm_header, day_parts_on
):
    a = setup_author()
    _, sub = _make_sub_activity(
        client, pm_header, benchmark_type="TASK_BASED", name="LUMPSUM",
        period_days=2,
    )
    payload = _split_payload(
        {"period_status": "leave"},
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id, sub["id"])]},
    )
    created = client.post(BASE, headers=a["header"], json=payload).json()
    task = created["tasks"][0]
    started = date.fromisoformat(task["started_date"])
    due = date.fromisoformat(task["due_date"])
    # due = started + (period_days - 1): the half period does NOT shrink or
    # scale the task deadline.
    assert started == date.fromisoformat(TODAY)
    assert (due - started).days == 1


def test_update_with_periods_rewrites_report(client, setup_author, day_parts_on):
    a = setup_author()
    created = client.post(BASE, headers=a["header"], json={
        "report_date": TODAY, "day_status": "work_at_office", "location": "chennai",
        "tasks": [_task(a["project"].id)],
    }).json()
    assert created["report_mode"] == "full_day"
    updated = client.patch(f"{BASE}/{created['id']}", headers=a["header"], json=_split_payload(
        {"period_status": "leave"},
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id)]},
    )).json()
    assert updated["report_mode"] == "split_day"
    assert updated["day_status"] == "half_day"
    assert len(updated["periods"]) == 2
    # And a legacy tasks update collapses it back to one Full-Day period.
    collapsed = client.patch(f"{BASE}/{created['id']}", headers=a["header"], json={
        "day_status": "work_at_office",
        "tasks": [_task(a["project"].id)],
    }).json()
    assert collapsed["report_mode"] == "full_day"
    assert len(collapsed["periods"]) == 1
    assert collapsed["tasks"][0]["period_id"] == collapsed["periods"][0]["id"]


# ── activity request routing ────────────────────────────────────────────────

def test_activity_request_routes_to_requested_period(
    client, setup_author, pm_header, day_parts_on
):
    a = setup_author()
    _, sub1 = _make_sub_activity(client, pm_header, name="FIRST-SUB")
    _, sub2 = _make_sub_activity(client, pm_header, name="EXTRA-SUB")
    created = client.post(BASE, headers=a["header"], json=_split_payload(
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id, sub1["id"])]},
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id, sub1["id"])]},
    )).json()
    second_half = next(
        p for p in created["periods"] if p["day_part"] == "second_half"
    )
    req = client.post("/api/v1/activity-requests", headers=a["header"], json={
        "report_id": created["id"],
        "period_id": second_half["id"],
        "project_id": str(a["project"].id),
        "sub_activity_id": sub2["id"],
    })
    assert req.status_code == 201, req.text
    assert req.json()["day_part"] == "second_half"

    approved = client.post(
        f"/api/v1/activity-requests/{req.json()['id']}/approve", headers=pm_header
    )
    assert approved.status_code == 200, approved.text
    detail = client.get(f"{BASE}/{created['id']}", headers=a["header"]).json()
    parts = {p["day_part"]: p for p in detail["periods"]}
    subs_in_second = [t["sub_activity_id"] for t in parts["second_half"]["tasks"]]
    assert sub2["id"] in subs_in_second
    assert len(parts["first_half"]["tasks"]) == 1


def test_activity_request_rejects_nonworking_period(
    client, setup_author, pm_header, day_parts_on
):
    a = setup_author()
    _, sub1 = _make_sub_activity(client, pm_header, name="W-SUB")
    _, sub2 = _make_sub_activity(client, pm_header, name="X-SUB")
    created = client.post(BASE, headers=a["header"], json=_split_payload(
        {"period_status": "leave"},
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id, sub1["id"])]},
    )).json()
    leave_period = next(
        p for p in created["periods"] if p["day_part"] == "first_half"
    )
    res = client.post("/api/v1/activity-requests", headers=a["header"], json={
        "report_id": created["id"],
        "period_id": leave_period["id"],
        "project_id": str(a["project"].id),
        "sub_activity_id": sub2["id"],
    })
    assert res.status_code == 422


# ── Activity Lead partial visibility on a split report ─────────────────────

def test_lead_sees_only_led_rows_of_split_report(
    client, db, setup_author, pm_header, day_parts_on,
    make_user, make_employee,
):
    """A Lead viewing a foreign split report sees only the led half's row; the
    periods metadata stays intact but the unled half's tasks are trimmed."""
    from app.modules.projects import service as proj_svc
    from app.modules.projects.schemas import ActivityMemberCreate
    from app.modules.users.models import User
    from app.modules.work_reports import service as wr_svc
    from sqlalchemy import select as sa_select

    a = setup_author()
    led_act, led_sub = _make_sub_activity(client, pm_header, name="LED-SUB")
    _, other_sub = _make_sub_activity(client, pm_header, name="OTHER-SUB")

    lead_u = make_user("lead@x.com")
    lead_e = make_employee(employee_code="LD-1", user_id=lead_u.id)
    pm_user = db.execute(
        sa_select(User).where(User.email == "pm@x.com")
    ).scalar_one()
    proj_svc.assign_activity_member(
        db, pm_user, a["project"].id, led_act["id"],
        ActivityMemberCreate(employee_id=lead_e.id, role="lead"),
    )

    created = client.post(BASE, headers=a["header"], json=_split_payload(
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id, led_sub["id"])]},
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id, other_sub["id"])]},
    )).json()
    client.post(f"{BASE}/{created['id']}/submit", headers=a["header"])

    out = wr_svc.get_work_report(db, lead_u, created["id"])
    assert out.scoped_to_led_activities is True
    assert [str(t.sub_activity_id) for t in out.tasks] == [led_sub["id"]]
    parts = {p.day_part: p for p in out.periods}
    assert set(parts) == {"first_half", "second_half"}
    assert len(parts["first_half"].tasks) == 1
    assert parts["second_half"].tasks == []


# ── compliance fractions (warn-only) ────────────────────────────────────────

def test_compliance_reports_fraction_mismatch_as_warning(
    client, db, setup_author, pm_header, day_parts_on, make_attendance
):
    a = setup_author()
    make_attendance(employee_id=a["emp"].id, attendance_date=date.today())
    _, sub = _make_sub_activity(client, pm_header, name="C-SUB")
    created = client.post(BASE, headers=a["header"], json=_split_payload(
        {"period_status": "leave"},
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id, sub["id"])]},
    )).json()
    client.post(f"{BASE}/{created['id']}/submit", headers=a["header"])

    out = client.get("/api/v1/report-compliance/me", headers=a["header"]).json()
    # The date-level requirement stays satisfied — one submitted header.
    assert out["has_report_today"] is True
    # Warn-only fraction comparison: reported 0.5 vs attendance-implied 1.0.
    assert out["reported_work_fraction_today"] == 0.5
    assert out["attendance_work_fraction_today"] == 1.0
    assert out["fraction_mismatch_today"] is True


def test_compliance_matching_fractions_no_warning(
    client, setup_author, pm_header, make_attendance
):
    a = setup_author()
    make_attendance(employee_id=a["emp"].id, attendance_date=date.today())
    _, sub = _make_sub_activity(client, pm_header, name="C2-SUB")
    created = client.post(BASE, headers=a["header"], json={
        "report_date": TODAY, "day_status": "work_at_office", "location": "chennai",
        "tasks": [_task(a["project"].id, sub["id"])],
    }).json()
    client.post(f"{BASE}/{created['id']}/submit", headers=a["header"])
    out = client.get("/api/v1/report-compliance/me", headers=a["header"]).json()
    assert out["reported_work_fraction_today"] == 1.0
    assert out["fraction_mismatch_today"] is False


# ── remarks: header (Full Day) vs periods (Split Day) ───────────────────────

def test_split_create_keeps_remarks_per_half_and_nulls_header(
    client, setup_author, day_parts_on
):
    a = setup_author()
    payload = _split_payload(
        {"period_status": "leave", "remarks": "Medical appointment"},
        {"period_status": "work_at_office", "location": "chennai",
         "remarks": "Completed MTL asset-photo verification",
         "tasks": [_task(a["project"].id)]},
    )
    # A stale header remark must never be stored on a split report.
    payload["remarks"] = "stale full-day remark"
    created = client.post(BASE, headers=a["header"], json=payload).json()
    assert created["remarks"] is None
    parts = {p["day_part"]: p for p in created["periods"]}
    assert parts["first_half"]["remarks"] == "Medical appointment"
    assert parts["second_half"]["remarks"] == "Completed MTL asset-photo verification"
    # Reopen: each remark still under its own half.
    fetched = client.get(f"{BASE}/{created['id']}", headers=a["header"]).json()
    parts = {p["day_part"]: p for p in fetched["periods"]}
    assert parts["first_half"]["remarks"] == "Medical appointment"
    assert parts["second_half"]["remarks"] == "Completed MTL asset-photo verification"


def test_split_update_nulls_header_remarks(client, setup_author, day_parts_on):
    a = setup_author()
    created = client.post(BASE, headers=a["header"], json={
        "report_date": TODAY, "day_status": "work_at_office", "location": "chennai",
        "remarks": "my full-day note",
        "tasks": [_task(a["project"].id)],
    }).json()
    assert created["remarks"] == "my full-day note"
    body = _split_payload(
        {"period_status": "leave", "remarks": "AM leave"},
        {"period_status": "work_at_office", "location": "chennai",
         "remarks": "PM work",
         "tasks": [_task(a["project"].id)]},
    )
    body["remarks"] = "my full-day note"  # stale header value re-sent
    updated = client.patch(f"{BASE}/{created['id']}", headers=a["header"], json=body).json()
    assert updated["remarks"] is None
    parts = {p["day_part"]: p for p in updated["periods"]}
    assert parts["first_half"]["remarks"] == "AM leave"
    assert parts["second_half"]["remarks"] == "PM work"


def test_updating_one_half_remark_keeps_the_other(client, setup_author, day_parts_on):
    a = setup_author()
    created = client.post(BASE, headers=a["header"], json=_split_payload(
        {"period_status": "work_at_office", "location": "chennai",
         "remarks": "first original", "tasks": [_task(a["project"].id)]},
        {"period_status": "work_at_office", "location": "chennai",
         "remarks": "second original", "tasks": [_task(a["project"].id)]},
    )).json()
    updated = client.patch(f"{BASE}/{created['id']}", headers=a["header"], json=_split_payload(
        {"period_status": "work_at_office", "location": "chennai",
         "remarks": "first original", "tasks": [_task(a["project"].id)]},
        {"period_status": "work_at_office", "location": "chennai",
         "remarks": "second EDITED", "tasks": [_task(a["project"].id)]},
    )).json()
    parts = {p["day_part"]: p for p in updated["periods"]}
    assert parts["first_half"]["remarks"] == "first original"
    assert parts["second_half"]["remarks"] == "second EDITED"


def test_period_order_in_payload_never_swaps_remarks(
    client, setup_author, day_parts_on
):
    a = setup_author()
    # Periods deliberately listed second-half first.
    payload = {
        "report_date": TODAY,
        "report_mode": "split_day",
        "periods": [
            {"day_part": "second_half", "period_status": "work_at_office",
             "location": "chennai", "remarks": "PM work",
             "tasks": [_task(a["project"].id)]},
            {"day_part": "first_half", "period_status": "leave",
             "remarks": "AM leave"},
        ],
    }
    created = client.post(BASE, headers=a["header"], json=payload).json()
    parts = {p["day_part"]: p for p in created["periods"]}
    assert parts["first_half"]["remarks"] == "AM leave"
    assert parts["second_half"]["remarks"] == "PM work"


def test_period_remarks_are_optional(client, setup_author, day_parts_on):
    a = setup_author()
    created = client.post(BASE, headers=a["header"], json=_split_payload(
        {"period_status": "comp_off"},
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id)]},
    )).json()
    parts = {p["day_part"]: p for p in created["periods"]}
    assert parts["first_half"]["remarks"] is None
    assert parts["second_half"]["remarks"] is None


def test_full_day_header_remarks_unchanged(client, setup_author):
    a = setup_author()
    created = client.post(BASE, headers=a["header"], json={
        "report_date": TODAY, "day_status": "work_at_office", "location": "chennai",
        "remarks": "classic day remark",
        "tasks": [_task(a["project"].id)],
    }).json()
    assert created["remarks"] == "classic day remark"
    # Legacy full-day periods never mirror the header remark.
    assert created["periods"][0]["remarks"] is None
    updated = client.patch(f"{BASE}/{created['id']}", headers=a["header"], json={
        "remarks": "edited day remark",
    }).json()
    assert updated["remarks"] == "edited day remark"


# ── mode isolation: Full-Day and split periods never coexist ────────────────

def test_full_day_and_half_periods_cannot_coexist(client, setup_author, day_parts_on):
    a = setup_author()
    payload = {
        "report_date": TODAY,
        "periods": [
            {"day_part": "full_day", "period_status": "work_at_office",
             "location": "chennai", "tasks": [_task(a["project"].id)]},
            {"day_part": "first_half", "period_status": "leave"},
            {"day_part": "second_half", "period_status": "work_at_office",
             "location": "chennai", "tasks": [_task(a["project"].id)]},
        ],
    }
    res = client.post(BASE, headers=a["header"], json=payload)
    assert res.status_code == 422


def test_legacy_task_list_ignored_when_periods_supplied(
    client, setup_author, day_parts_on
):
    """A hidden legacy `tasks` collection must not survive alongside periods —
    only the tasks nested in each period become rows."""
    a = setup_author()
    payload = _split_payload(
        {"period_status": "leave"},
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id)]},
    )
    payload["tasks"] = [_task(a["project"].id), _task(a["project"].id)]
    created = client.post(BASE, headers=a["header"], json=payload).json()
    assert len(created["tasks"]) == 1
    assert created["tasks"][0]["day_part"] == "second_half"


def test_mode_conversion_replaces_period_structure_wholesale(
    client, setup_author, day_parts_on
):
    """Converting a draft's mode rewrites periods + tasks; nothing from the
    old mode leaks through."""
    a = setup_author()
    created = client.post(BASE, headers=a["header"], json={
        "report_date": TODAY, "day_status": "work_at_office", "location": "chennai",
        "tasks": [_task(a["project"].id), _task(a["project"].id)],
    }).json()
    assert len(created["tasks"]) == 2
    converted = client.patch(f"{BASE}/{created['id']}", headers=a["header"], json=_split_payload(
        {"period_status": "leave"},
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(a["project"].id)]},
    )).json()
    assert converted["report_mode"] == "split_day"
    assert {p["day_part"] for p in converted["periods"]} == {"first_half", "second_half"}
    assert len(converted["tasks"]) == 1
    assert converted["tasks"][0]["day_part"] == "second_half"
    # And back: a legacy full-day update collapses to one Full-Day period.
    back = client.patch(f"{BASE}/{created['id']}", headers=a["header"], json={
        "day_status": "work_at_office", "location": "chennai",
        "tasks": [_task(a["project"].id)],
    }).json()
    assert back["report_mode"] == "full_day"
    assert [p["day_part"] for p in back["periods"]] == ["full_day"]
    assert len(back["tasks"]) == 1
