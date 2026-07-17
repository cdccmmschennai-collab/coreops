"""Tests for the benchmark engine: compute_benchmark/compute_overdue unit
cases + the work-report submit-path integration (snapshotting, NUMERIC vs
TASK_BASED vs legacy/no-benchmark rows, and the TASK_BASED due-date /
completion-toggle workflow)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.modules.activity_master.service import compute_benchmark, compute_overdue
from app.modules.notifications.models import Notification
from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole

BASE = "/api/v1/work-reports"
TODAY_D = date.today()
TODAY = TODAY_D.isoformat()


# ── compute_benchmark unit tests ────────────────────────────────────────────

def test_numeric_under_benchmark_has_deficit():
    deficit, pct = compute_benchmark("NUMERIC", Decimal("250"), 200)
    assert deficit == Decimal("50")
    assert pct == Decimal("80")


def test_numeric_meets_benchmark_zero_deficit():
    deficit, pct = compute_benchmark("NUMERIC", Decimal("250"), 250)
    assert deficit == Decimal("0")
    assert pct == Decimal("100")


def test_numeric_exceeds_benchmark_zero_deficit_over_100_pct():
    deficit, pct = compute_benchmark("NUMERIC", Decimal("250"), 300)
    assert deficit == Decimal("0")
    assert pct == Decimal("120")


def test_numeric_with_no_actual_count_full_deficit():
    deficit, pct = compute_benchmark("NUMERIC", Decimal("250"), None)
    assert deficit == Decimal("250")
    assert pct == Decimal("0")


def test_task_based_never_computes():
    deficit, pct = compute_benchmark("TASK_BASED", None, 100)
    assert (deficit, pct) == (None, None)


def test_no_benchmark_type_never_computes():
    deficit, pct = compute_benchmark(None, None, 100)
    assert (deficit, pct) == (None, None)


def test_zero_benchmark_value_never_computes():
    deficit, pct = compute_benchmark("NUMERIC", Decimal("0"), 100)
    assert (deficit, pct) == (None, None)


# ── compute_overdue unit tests ──────────────────────────────────────────────

def test_overdue_when_past_due_and_not_completed():
    is_overdue, days = compute_overdue(TODAY_D - timedelta(days=3), False, TODAY_D)
    assert is_overdue is True
    assert days == 3


def test_not_overdue_when_due_today():
    is_overdue, days = compute_overdue(TODAY_D, False, TODAY_D)
    assert (is_overdue, days) == (False, 0)


def test_not_overdue_when_completed_even_if_past_due():
    is_overdue, days = compute_overdue(TODAY_D - timedelta(days=5), True, TODAY_D)
    assert (is_overdue, days) == (False, 0)


def test_not_overdue_when_no_due_date():
    is_overdue, days = compute_overdue(None, False, TODAY_D)
    assert (is_overdue, days) == (False, 0)


def test_not_overdue_when_due_in_future():
    is_overdue, days = compute_overdue(TODAY_D + timedelta(days=2), False, TODAY_D)
    assert (is_overdue, days) == (False, 0)


# ── submit-path integration ─────────────────────────────────────────────────

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
def activity_admin(auth_header):
    return auth_header(email="pm@x.com", role=UserRole.project_manager)


def _make_sub_activity(
    client, admin_header, *, benchmark_type=None, benchmark_value=None,
    relevant_count_field=None, name="Sub",
):
    a = client.post(
        "/api/v1/activity-master/activities", json={"name": f"Activity for {name}"}, headers=admin_header
    ).json()
    body = {"name": name}
    if benchmark_type:
        body["benchmark_type"] = benchmark_type
    if benchmark_value is not None:
        body["benchmark_value"] = benchmark_value
    if relevant_count_field is not None:
        body["relevant_count_field"] = relevant_count_field
    sub = client.post(
        f"/api/v1/activity-master/activities/{a['id']}/sub-activities", json=body, headers=admin_header
    ).json()
    return a, sub


def test_submit_computes_deficit_for_numeric_sub_activity(client, setup_author, activity_admin):
    a = setup_author()
    _, sub = _make_sub_activity(
        client, activity_admin, benchmark_type="NUMERIC", benchmark_value=250,
        relevant_count_field="tags", name="FMTL-REWORK",
    )
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "sub_activity_id": sub["id"], "tags_count": 200,
        }],
    }
    created = client.post(BASE, headers=a["header"], json=payload).json()
    # Draft: not yet computed.
    assert created["tasks"][0]["deficit"] is None

    report_id = created["id"]
    submitted = client.post(f"{BASE}/{report_id}/submit", headers=a["header"]).json()
    task = submitted["tasks"][0]
    assert task["benchmark_type_snapshot"] == "NUMERIC"
    assert float(task["benchmark_value_snapshot"]) == 250.0
    assert task["relevant_count_field_snapshot"] == "tags"
    assert task["tags_count"] == 200  # operational reporting: unchanged, read directly
    assert float(task["deficit"]) == 50.0
    assert float(task["productivity_pct"]) == 80.0
    assert task["activity_name"] is not None
    assert task["sub_activity_name"] == "FMTL-REWORK"
    # activity_type auto-derived for backward compat with legacy views.
    assert "FMTL-REWORK" in task["activity_type"]


def test_submit_uses_docs_count_when_relevant_field_is_docs(client, setup_author, activity_admin):
    """Confirms the engine reads the *correct* count column, not just tags —
    each NUMERIC sub-activity points at exactly one of the 4 existing fields."""
    a = setup_author()
    _, sub = _make_sub_activity(
        client, activity_admin, benchmark_type="NUMERIC", benchmark_value=500,
        relevant_count_field="docs", name="DOC IDB-QC",
    )
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "sub_activity_id": sub["id"], "docs_count": 400, "tags_count": 999,
        }],
    }
    created = client.post(BASE, headers=a["header"], json=payload).json()
    submitted = client.post(f"{BASE}/{created['id']}/submit", headers=a["header"]).json()
    task = submitted["tasks"][0]
    assert task["relevant_count_field_snapshot"] == "docs"
    # 500 - 400 = 100, NOT influenced by the (irrelevant) tags_count=999.
    assert float(task["deficit"]) == 100.0


def test_task_based_due_date_computed_on_draft_save(client, setup_author, activity_admin):
    """started_date/due_date are computed immediately on draft save, not
    deferred to submit — there's no mutable 'actual entry' to wait for."""
    a = setup_author()
    _, sub = _make_sub_activity(
        client, activity_admin, benchmark_type="TASK_BASED", name="DOC IDB-AUDIT QUERY",
    )
    res = client.patch(
        f"/api/v1/activity-master/sub-activities/{sub['id']}",
        json={"benchmark_period_days": 2}, headers=activity_admin,
    )
    assert res.status_code == 200
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "sub_activity_id": sub["id"],
        }],
    }
    created = client.post(BASE, headers=a["header"], json=payload).json()
    task = created["tasks"][0]
    assert task["started_date"] == TODAY
    # 2-day activity spans the report day + the next day → due report_date + 1.
    assert task["due_date"] == (TODAY_D + timedelta(days=1)).isoformat()
    assert task["is_completed"] is False
    assert task["completed_date"] is None
    assert task["is_overdue"] is False


def test_task_based_daily_due_date_is_assigned_date(client, setup_author, activity_admin):
    """A daily benchmark activity (period 1, the default) is due the SAME day it
    is reported — never pushed to the next day."""
    a = setup_author()
    _, sub = _make_sub_activity(
        client, activity_admin, benchmark_type="TASK_BASED", name="MTL-ASSET PHOTO",
    )
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "sub_activity_id": sub["id"],
        }],
    }
    created = client.post(BASE, headers=a["header"], json=payload).json()
    task = created["tasks"][0]
    assert task["started_date"] == TODAY
    assert task["due_date"] == TODAY        # same day, not TODAY + 1
    assert task["is_overdue"] is False


def test_submit_task_based_sub_activity_has_no_deficit(client, setup_author, activity_admin):
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_type="TASK_BASED", name="DOC IDB-AUDIT QUERY")
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "sub_activity_id": sub["id"], "is_completed": True,
        }],
    }
    created = client.post(BASE, headers=a["header"], json=payload).json()
    submitted = client.post(f"{BASE}/{created['id']}/submit", headers=a["header"]).json()
    task = submitted["tasks"][0]
    assert task["benchmark_type_snapshot"] == "TASK_BASED"
    assert task["deficit"] is None
    assert task["productivity_pct"] is None
    assert task["is_completed"] is True
    assert task["completed_date"] == TODAY


def test_completion_toggle_works_on_submitted_locked_report(client, setup_author, activity_admin):
    """The key scenario this redesign exists for: completing a TASK_BASED
    item days after its report is already submitted and locked."""
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_type="TASK_BASED", name="CRS CORRECTION")
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "sub_activity_id": sub["id"],
        }],
    }
    created = client.post(BASE, headers=a["header"], json=payload).json()
    submitted = client.post(f"{BASE}/{created['id']}/submit", headers=a["header"]).json()
    assert submitted["status"] == "submitted"
    task_id = submitted["tasks"][0]["id"]
    assert submitted["tasks"][0]["is_completed"] is False

    res = client.patch(
        f"{BASE}/tasks/{task_id}/completion", json={"is_completed": True}, headers=a["header"],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["is_completed"] is True
    assert body["completed_date"] == TODAY

    # Report itself is untouched — still submitted, not reopened.
    refetched = client.get(f"{BASE}/{created['id']}", headers=a["header"]).json()
    assert refetched["status"] == "submitted"
    assert refetched["tasks"][0]["is_completed"] is True


def test_completion_toggle_rejects_non_author(client, setup_author, activity_admin):
    a = setup_author(email="owner@x.com", code="E-OWN")
    other = setup_author(email="other@x.com", code="E-OTH", proj_code="P-OTH")
    _, sub = _make_sub_activity(client, activity_admin, benchmark_type="TASK_BASED", name="OVS CORRECTION")
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "sub_activity_id": sub["id"],
        }],
    }
    created = client.post(BASE, headers=a["header"], json=payload).json()
    task_id = created["tasks"][0]["id"]
    res = client.patch(
        f"{BASE}/tasks/{task_id}/completion", json={"is_completed": True}, headers=other["header"],
    )
    assert res.status_code == 403


def test_overdue_flips_true_after_due_date_passes(client, db, setup_author, activity_admin):
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_type="TASK_BASED", name="PUNCH LIST")
    client.patch(
        f"/api/v1/activity-master/sub-activities/{sub['id']}",
        json={"benchmark_period_days": 1}, headers=activity_admin,
    )
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "sub_activity_id": sub["id"],
        }],
    }
    created = client.post(BASE, headers=a["header"], json=payload).json()
    assert created["tasks"][0]["is_overdue"] is False  # due_date is today+1, not overdue yet

    # Simulate time passing: due_date is now in the past.
    from app.modules.work_reports.models import WorkReportTask
    row = db.get(WorkReportTask, created["tasks"][0]["id"])
    row.due_date = TODAY_D - timedelta(days=3)
    db.add(row)
    db.commit()

    refetched = client.get(f"{BASE}/{created['id']}", headers=a["header"]).json()
    assert refetched["tasks"][0]["is_overdue"] is True
    assert refetched["tasks"][0]["days_overdue"] == 3


def test_submit_legacy_row_without_sub_activity_does_not_error(client, setup_author):
    """A row with no sub_activity_id (legacy free-text activity_type) must still
    submit cleanly with no benchmark fields populated."""
    a = setup_author()
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "activity_type": "Some legacy free text",
        }],
    }
    created = client.post(BASE, headers=a["header"], json=payload).json()
    submitted = client.post(f"{BASE}/{created['id']}/submit", headers=a["header"]).json()
    task = submitted["tasks"][0]
    assert task["activity_type"] == "Some legacy free text"
    assert task["sub_activity_id"] is None
    assert task["deficit"] is None
    assert task["productivity_pct"] is None


def test_inactive_sub_activity_rejected_on_create(client, setup_author, activity_admin):
    a = setup_author()
    _, sub = _make_sub_activity(
        client, activity_admin, benchmark_type="NUMERIC", benchmark_value=100,
        relevant_count_field="tags", name="X",
    )
    client.delete(f"/api/v1/activity-master/sub-activities/{sub['id']}", headers=activity_admin)
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "sub_activity_id": sub["id"], "tags_count": 10,
        }],
    }
    res = client.post(BASE, headers=a["header"], json=payload)
    assert res.status_code == 422


# ── get_daily_benchmark_ledger / get_overdue_activities (live, no storage) ──

def test_daily_pending_is_flat_per_day_and_resets_next_week(client, db, setup_author, activity_admin):
    """250/day benchmark, 200/day actual every day: each day's pending is a
    flat 50 (not a growing cumulative total) — that's the daily-ledger
    redesign. The week's total (sum of daily rows) is still 250, matching
    the old cumulative model only because there's no surplus day here."""
    from app.modules.activity_master.service import get_daily_benchmark_ledger

    a = setup_author()
    _, sub = _make_sub_activity(
        client, activity_admin, benchmark_type="NUMERIC", benchmark_value=250,
        relevant_count_field="tags", name="FMTL-REWORK",
    )
    # A fully past cycle (the previous Fri..Thu) so every report_date <= today
    # (the API rejects future report dates) while staying inside the
    # current/previous-month edit window. Weekdays only: Fri, then Mon..Thu.
    from app.modules.activity_master.service import compute_week_bounds

    prev_friday = compute_week_bounds(TODAY_D)[0] - timedelta(days=7)
    workdays = [prev_friday + timedelta(days=o) for o in (0, 3, 4, 5, 6)]
    for i, report_date in enumerate(workdays):
        payload = {
            "report_date": report_date.isoformat(),
            "tasks": [{
                "project_id": str(a["project"].id), "description": "work",
                "sub_activity_id": sub["id"], "tags_count": 200,
            }],
        }
        created = client.post(BASE, headers=a["header"], json=payload).json()
        client.post(f"{BASE}/{created['id']}/submit", headers=a["header"])

        ledger = get_daily_benchmark_ledger(db, employee_ids={a["emp"].id}, today=report_date)
        assert len(ledger) == i + 1  # one row per elapsed day so far
        today_row = next(r for r in ledger if r["date"] == report_date)
        assert float(today_row["target"]) == 250
        assert float(today_row["actual"]) == 200
        assert float(today_row["pending"]) == 50  # flat, not cumulative
        assert today_row["benchmark_unit"] == "tags"

    cycle_thursday = prev_friday + timedelta(days=6)
    full_week = get_daily_benchmark_ledger(db, employee_ids={a["emp"].id}, today=cycle_thursday)
    assert len(full_week) == 5
    assert sum(float(r["pending"]) for r in full_week) == 250
    assert sum(float(r["actual"]) for r in full_week) == 1000
    assert sum(float(r["target"]) for r in full_week) == 1250

    next_friday = prev_friday + timedelta(days=7)
    ledger_next_week = get_daily_benchmark_ledger(db, employee_ids={a["emp"].id}, today=next_friday)
    assert ledger_next_week == []  # no submissions yet this new cycle — clean reset


def test_daily_pending_does_not_let_a_surplus_day_offset_a_deficit_day(client, db, setup_author, activity_admin):
    """120/day benchmark over the previous Fri..Thu cycle's five weekdays;
    100, 110, 90, 130 (surplus), 120. Per-day pending: 20, 10, 30, 0, 0 ->
    weekly total 60. A cumulative model would have netted the surplus day's
    +10 against the cycle's total and landed on 50 instead — the daily
    ledger must NOT do that."""
    from app.modules.activity_master.service import (
        compute_week_bounds,
        get_daily_benchmark_ledger,
    )

    a = setup_author()
    _, sub = _make_sub_activity(
        client, activity_admin, benchmark_type="NUMERIC", benchmark_value=120,
        relevant_count_field="tags", name="FMTL-REWORK",
    )
    prev_friday = compute_week_bounds(TODAY_D)[0] - timedelta(days=7)
    workdays = [prev_friday + timedelta(days=o) for o in (0, 3, 4, 5, 6)]
    counts = [100, 110, 90, 130, 120]
    expected_daily_pending = [20, 10, 30, 0, 0]
    for report_date, count in zip(workdays, counts):
        payload = {
            "report_date": report_date.isoformat(),
            "tasks": [{
                "project_id": str(a["project"].id), "description": "work",
                "sub_activity_id": sub["id"], "tags_count": count,
            }],
        }
        created = client.post(BASE, headers=a["header"], json=payload).json()
        client.post(f"{BASE}/{created['id']}/submit", headers=a["header"])

    cycle_thursday = prev_friday + timedelta(days=6)
    ledger = get_daily_benchmark_ledger(db, employee_ids={a["emp"].id}, today=cycle_thursday)
    assert len(ledger) == 5
    by_date = {r["date"]: r for r in ledger}
    for report_date, expected in zip(workdays, expected_daily_pending):
        assert float(by_date[report_date]["pending"]) == expected

    weekly_pending_total = sum(float(r["pending"]) for r in ledger)
    assert weekly_pending_total == 60  # not 50 — no cross-day netting


def test_daily_ledger_omits_skipped_day_no_synthetic_rows(client, db, setup_author, activity_admin):
    """An employee who reports Monday and Wednesday but skips Tuesday gets
    rows only for the days actually reported — Tuesday is absent, not
    synthesized as a zero-actual / full-pending row. Benchmark performance
    reflects only activities actually reported."""
    from app.modules.activity_master.service import get_daily_benchmark_ledger

    a = setup_author()
    _, sub = _make_sub_activity(
        client, activity_admin, benchmark_type="NUMERIC", benchmark_value=250,
        relevant_count_field="tags", name="FMTL-REWORK",
    )
    this_week_monday = TODAY_D - timedelta(days=TODAY_D.weekday())
    monday = this_week_monday - timedelta(days=7)
    for offset in (0, 2):  # Monday, Wednesday — Tuesday skipped entirely
        report_date = monday + timedelta(days=offset)
        payload = {
            "report_date": report_date.isoformat(),
            "tasks": [{
                "project_id": str(a["project"].id), "description": "work",
                "sub_activity_id": sub["id"], "tags_count": 200,
            }],
        }
        created = client.post(BASE, headers=a["header"], json=payload).json()
        client.post(f"{BASE}/{created['id']}/submit", headers=a["header"])

    wednesday = monday + timedelta(days=2)
    ledger = get_daily_benchmark_ledger(db, employee_ids={a["emp"].id}, today=wednesday)
    assert len(ledger) == 2  # Mon, Wed only — skipped Tuesday is not synthesized
    dates = {r["date"] for r in ledger}
    assert dates == {monday, wednesday}
    assert (monday + timedelta(days=1)) not in dates  # no Tuesday row
    for r in ledger:
        assert float(r["actual"]) == 200
        assert float(r["pending"]) == 50


def test_daily_ledger_scoped_by_employee_ids(client, db, setup_author, activity_admin):
    from app.modules.activity_master.service import get_daily_benchmark_ledger

    a = setup_author(email="emp1@x.com", code="E-1")
    other = setup_author(email="emp2@x.com", code="E-2", proj_code="P-2")
    _, sub = _make_sub_activity(
        client, activity_admin, benchmark_type="NUMERIC", benchmark_value=100,
        relevant_count_field="tags", name="X",
    )
    for actor in (a, other):
        payload = {
            "report_date": TODAY,
            "tasks": [{
                "project_id": str(actor["project"].id), "description": "work",
                "sub_activity_id": sub["id"], "tags_count": 10,
            }],
        }
        created = client.post(BASE, headers=actor["header"], json=payload).json()
        client.post(f"{BASE}/{created['id']}/submit", headers=actor["header"])

    scoped = get_daily_benchmark_ledger(db, employee_ids={a["emp"].id}, today=TODAY_D)
    assert all(r["employee_id"] == a["emp"].id for r in scoped)
    assert len(scoped) >= 1

    empty = get_daily_benchmark_ledger(db, employee_ids=set(), today=TODAY_D)
    assert empty == []


def test_overdue_activities_lists_past_due_incomplete_rows(client, db, setup_author, activity_admin):
    """Overdue is scoped to the CURRENT Fri..Thu cycle (week_start <= due_date <
    today), so both dates here are anchored to the cycle rather than to the real
    calendar date.

    The earlier `due = today - 2 days` was fragile: on a Friday or Saturday the
    cycle has only just begun, so a deadline two days ago belongs to the
    *previous* cycle and is correctly excluded — the test failed on those two
    days while the product behaved exactly as designed. Anchoring to
    compute_week_bounds keeps the assertion honest on all seven days. The
    Friday-reset behaviour itself is unchanged and still enforced by
    test_overdue_excludes_previous_cycle below."""
    from app.modules.activity_master.service import (
        compute_week_bounds,
        get_overdue_activities,
    )
    from app.modules.work_reports.models import WorkReportTask

    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_type="TASK_BASED", name="AUDIT QUERY")
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "sub_activity_id": sub["id"],
        }],
    }
    created = client.post(BASE, headers=a["header"], json=payload).json()
    # Due today (1-day activity) -> not yet overdue.
    assert get_overdue_activities(db, employee_ids={a["emp"].id}, today=TODAY_D) == []

    # A deadline on the cycle's first day, evaluated two days into that same
    # cycle: inside the window (due_date >= week_start) and past (due_date <
    # today) on every calendar day.
    week_start, _ = compute_week_bounds(TODAY_D)
    as_of = week_start + timedelta(days=2)
    row = db.get(WorkReportTask, created["tasks"][0]["id"])
    row.due_date = week_start
    db.add(row)
    db.commit()

    overdue = get_overdue_activities(db, employee_ids={a["emp"].id}, today=as_of)
    assert len(overdue) == 1
    assert overdue[0]["sub_activity_name"] == "AUDIT QUERY"
    assert overdue[0]["days_overdue"] == 2

    # Completing it removes it from the live overdue list.
    client.patch(
        f"{BASE}/tasks/{created['tasks'][0]['id']}/completion",
        json={"is_completed": True}, headers=a["header"],
    )
    assert get_overdue_activities(db, employee_ids={a["emp"].id}, today=as_of) == []


def test_overdue_excludes_previous_cycle(client, db, setup_author, activity_admin):
    """The Friday reset, asserted directly: a deadline in the previous cycle is
    never reported as overdue, however long it has been open. This is the
    behaviour that made the old date arithmetic above look broken, so it is now
    pinned by its own test rather than left implicit."""
    from app.modules.activity_master.service import (
        compute_week_bounds,
        get_overdue_activities,
    )
    from app.modules.work_reports.models import WorkReportTask

    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_type="TASK_BASED", name="STALE")
    created = client.post(
        BASE, headers=a["header"],
        json={"report_date": TODAY, "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "sub_activity_id": sub["id"],
        }]},
    ).json()

    week_start, _ = compute_week_bounds(TODAY_D)
    row = db.get(WorkReportTask, created["tasks"][0]["id"])
    row.due_date = week_start - timedelta(days=1)  # last cycle's Thursday
    db.add(row)
    db.commit()

    assert get_overdue_activities(db, employee_ids={a["emp"].id}, today=TODAY_D) == []


def test_no_persisted_notification_on_benchmark_shortfall(client, db, setup_author, activity_admin):
    """Confirms the old submit-time NUMERIC_BENCHMARK notification was
    removed in favor of the live queries above."""
    a = setup_author()
    _, sub = _make_sub_activity(
        client, activity_admin, benchmark_type="NUMERIC", benchmark_value=250,
        relevant_count_field="tags", name="FMTL-REWORK",
    )
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "sub_activity_id": sub["id"], "tags_count": 200,
        }],
    }
    created = client.post(BASE, headers=a["header"], json=payload).json()
    client.post(f"{BASE}/{created['id']}/submit", headers=a["header"])

    rows = db.execute(
        select(Notification).where(
            Notification.user_id == a["user"].id,
            Notification.type == "NUMERIC_BENCHMARK",
        )
    ).scalars().all()
    assert rows == []
