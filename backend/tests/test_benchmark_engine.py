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
    assert task["due_date"] == (TODAY_D + timedelta(days=2)).isoformat()
    assert task["is_completed"] is False
    assert task["completed_date"] is None
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


# ── NUMERIC_BENCHMARK notification upsert/resolve on submit ────────────────

def test_submit_under_benchmark_creates_notification(client, db, setup_author, activity_admin):
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

    notif = db.execute(
        select(Notification).where(
            Notification.user_id == a["user"].id,
            Notification.type == "NUMERIC_BENCHMARK",
        )
    ).scalar_one()
    assert notif.severity == "WARNING"
    assert notif.resolved_at is None
    assert "50" in notif.message


def test_resubmit_meeting_benchmark_resolves_notification(client, db, setup_author, activity_admin):
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

    # Reviewer sends it back, author fixes the count and resubmits.
    client.post(
        f"{BASE}/{created['id']}/reject", json={"review_note": "fix count"}, headers=activity_admin,
    )
    client.patch(
        f"{BASE}/{created['id']}",
        json={"tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "sub_activity_id": sub["id"], "tags_count": 250,
        }]},
        headers=a["header"],
    )
    client.post(f"{BASE}/{created['id']}/submit", headers=a["header"])

    notif = db.execute(
        select(Notification).where(
            Notification.user_id == a["user"].id,
            Notification.type == "NUMERIC_BENCHMARK",
        )
    ).scalar_one()
    assert notif.resolved_at is not None


def test_upsert_notification_updates_existing_row_in_place(client, db, setup_author, activity_admin):
    """Two consecutive shortfalls for the same sub-activity update one
    notification row rather than creating a second one."""
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
    client.post(
        f"{BASE}/{created['id']}/reject", json={"review_note": "n/a"}, headers=activity_admin,
    )
    client.patch(
        f"{BASE}/{created['id']}",
        json={"tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "sub_activity_id": sub["id"], "tags_count": 150,
        }]},
        headers=a["header"],
    )
    client.post(f"{BASE}/{created['id']}/submit", headers=a["header"])

    rows = db.execute(
        select(Notification).where(
            Notification.user_id == a["user"].id,
            Notification.type == "NUMERIC_BENCHMARK",
        )
    ).scalars().all()
    assert len(rows) == 1
    assert "100" in rows[0].message  # latest deficit (250-150), not the first (50)
