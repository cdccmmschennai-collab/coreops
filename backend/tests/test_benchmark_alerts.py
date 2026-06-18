"""Tests for the Phase 2 Homepage Alerts endpoints (GET /benchmarks/my-alerts,
GET /benchmarks/team-alerts) — read-only views over the Phase 1 live engine.
No notifications, no persistence, no scheduled jobs."""
from datetime import date, timedelta

import pytest

from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole

BASE = "/api/v1/work-reports"
ALERTS_BASE = "/api/v1/benchmarks"
TODAY_D = date.today()
TODAY = TODAY_D.isoformat()


@pytest.fixture()
def setup_author(make_user, make_employee, make_project, make_project_member, login):
    def _make(*, email="emp@x.com", code="E-1", proj_code="P-1", first_name="Test", last_name="User"):
        u = make_user(email, role=UserRole.employee)
        e = make_employee(employee_code=code, user_id=u.id, first_name=first_name, last_name=last_name)
        p = make_project(code=proj_code, status=ProjectStatus.active)
        make_project_member(project_id=p.id, employee_id=e.id)
        return {"user": u, "emp": e, "project": p, "header": login(email)}

    return _make


@pytest.fixture()
def activity_admin(auth_header):
    return auth_header(email="pm@x.com", role=UserRole.project_manager)


def _make_sub_activity(
    client, admin_header, *, benchmark_type=None, benchmark_value=None,
    relevant_count_field=None, name="Sub", period_days=None,
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
    if period_days is not None:
        client.patch(
            f"/api/v1/activity-master/sub-activities/{sub['id']}",
            json={"benchmark_period_days": period_days}, headers=admin_header,
        )
    return a, sub


def test_my_alerts_empty_for_fresh_employee(client, setup_author):
    a = setup_author()
    res = client.get(ALERTS_BASE + "/my-alerts", headers=a["header"])
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "shortfalls": [], "daily": [], "overdue": [], "tasks": [],
        "summary": {"pending_benchmarks_count": 0, "overdue_activities_count": 0, "productivity_pct": None},
    }


def test_my_alerts_shows_shortfall_and_summary(client, setup_author, activity_admin):
    a = setup_author()
    _, sub = _make_sub_activity(
        client, activity_admin, benchmark_type="NUMERIC", benchmark_value=250,
        relevant_count_field="tags", name="FMTL Rework",
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

    body = client.get(ALERTS_BASE + "/my-alerts", headers=a["header"]).json()
    # Only the day actually reported produces a row — no synthesized
    # zero-actual rows for the other elapsed weekdays.
    assert len(body["shortfalls"]) == 1
    today_row = body["shortfalls"][0]
    assert today_row["date"] == TODAY
    assert today_row["sub_activity_name"] == "FMTL Rework"
    assert today_row["benchmark_unit"] == "tags"
    assert float(today_row["actual"]) == 200.0
    assert float(today_row["target"]) == 250.0
    assert float(today_row["pending"]) == 50.0
    assert body["summary"]["pending_benchmarks_count"] == 1
    assert body["summary"]["overdue_activities_count"] == 0
    # Productivity is over the reported day only: 200 / 250.
    assert float(body["summary"]["productivity_pct"]) == pytest.approx(200 / 250 * 100)


def test_my_alerts_daily_carries_project_and_hours(client, setup_author, activity_admin):
    a = setup_author()
    _, sub = _make_sub_activity(
        client, activity_admin, benchmark_type="NUMERIC", benchmark_value=120,
        relevant_count_field="tags", name="FMTL",
    )
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "sub_activity_id": sub["id"], "tags_count": 100, "minutes_spent": 480,
        }],
    }
    created = client.post(BASE, headers=a["header"], json=payload).json()
    client.post(f"{BASE}/{created['id']}/submit", headers=a["header"])

    body = client.get(ALERTS_BASE + "/my-alerts", headers=a["header"]).json()
    # `daily` carries every reported row (clean days included), unlike
    # `shortfalls` which only carries pending > 0 rows.
    today_row = next(r for r in body["daily"] if r["date"] == TODAY)
    assert today_row["project_name"] == a["project"].name
    assert today_row["hours_minutes"] == 480
    assert float(today_row["pending"]) == 20.0


def test_my_alerts_tasks_panel_is_current_week_only_and_includes_completed(
    client, db, setup_author, activity_admin,
):
    """The 'Pending Tasks (This Week)' panel is scoped to the current week
    (Mon..Fri): every task whose due_date falls inside the week shows up,
    completed or not. A task from a previous week (still pending or long
    overdue) is deliberately excluded — the employee dashboard never carries
    backlog forward across the week boundary, even though the row stays in
    the database."""
    from app.modules.activity_master.service import compute_week_bounds
    from app.modules.work_reports.models import WorkReportTask

    week_start, _week_end = compute_week_bounds(TODAY_D)

    a = setup_author()
    _, week_pending_sub = _make_sub_activity(client, activity_admin, benchmark_type="TASK_BASED", name="This Week Pending")
    _, week_done_sub = _make_sub_activity(client, activity_admin, benchmark_type="TASK_BASED", name="This Week Completed")
    _, last_week_sub = _make_sub_activity(client, activity_admin, benchmark_type="TASK_BASED", name="Last Week Pending")

    # Monday (in-week, pending), Tuesday (in-week, completed), and a day in the
    # previous week (still pending — must NOT appear).
    subs_and_due = (
        (week_pending_sub, week_start),
        (week_done_sub, week_start + timedelta(days=1)),
        (last_week_sub, week_start - timedelta(days=3)),
    )
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "sub_activity_id": sub["id"],
        } for sub, _ in subs_and_due],
    }
    created = client.post(BASE, headers=a["header"], json=payload).json()

    task_ids = {}
    for task, (sub, due) in zip(created["tasks"], subs_and_due):
        task_ids[sub["id"]] = task["id"]
        row = db.get(WorkReportTask, task["id"])
        row.due_date = due
        db.add(row)
    db.commit()

    client.patch(
        f"{BASE}/tasks/{task_ids[week_done_sub['id']]}/completion",
        json={"is_completed": True}, headers=a["header"],
    )

    body = client.get(ALERTS_BASE + "/my-alerts", headers=a["header"]).json()
    by_name = {t["sub_activity_name"]: t for t in body["tasks"]}
    assert set(by_name) == {"This Week Pending", "This Week Completed"}
    assert by_name["This Week Pending"]["status"] == "pending"
    assert by_name["This Week Completed"]["status"] == "completed"
    assert "Last Week Pending" not in by_name  # previous-week backlog never carries forward


def test_my_alerts_shows_overdue(client, db, setup_author, activity_admin):
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_type="TASK_BASED", name="Audit Query")
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "sub_activity_id": sub["id"],
        }],
    }
    created = client.post(BASE, headers=a["header"], json=payload).json()

    from app.modules.work_reports.models import WorkReportTask

    row = db.get(WorkReportTask, created["tasks"][0]["id"])
    row.due_date = TODAY_D - timedelta(days=2)
    db.add(row)
    db.commit()

    body = client.get(ALERTS_BASE + "/my-alerts", headers=a["header"]).json()
    assert len(body["overdue"]) == 1
    assert body["overdue"][0]["sub_activity_name"] == "Audit Query"
    assert body["overdue"][0]["days_overdue"] == 2
    assert body["summary"]["overdue_activities_count"] == 1

    client.patch(
        f"{BASE}/tasks/{created['tasks'][0]['id']}/completion",
        json={"is_completed": True}, headers=a["header"],
    )
    body_after = client.get(ALERTS_BASE + "/my-alerts", headers=a["header"]).json()
    assert body_after["overdue"] == []


def test_my_alerts_employee_cannot_see_others(client, setup_author, activity_admin):
    a = setup_author(email="a@x.com", code="E-A")
    other = setup_author(email="b@x.com", code="E-B", proj_code="P-B")
    _, sub = _make_sub_activity(
        client, activity_admin, benchmark_type="NUMERIC", benchmark_value=100,
        relevant_count_field="tags", name="X",
    )
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(other["project"].id), "description": "work",
            "sub_activity_id": sub["id"], "tags_count": 10,
        }],
    }
    created = client.post(BASE, headers=other["header"], json=payload).json()
    client.post(f"{BASE}/{created['id']}/submit", headers=other["header"])

    body = client.get(ALERTS_BASE + "/my-alerts", headers=a["header"]).json()
    assert body["shortfalls"] == []


def test_team_alerts_requires_pm_role(client, setup_author):
    a = setup_author()
    res = client.get(ALERTS_BASE + "/team-alerts", headers=a["header"])
    assert res.status_code == 403


def test_team_alerts_aggregates_across_employees(client, setup_author, activity_admin):
    alice = setup_author(email="alice@x.com", code="E-ALICE", first_name="Alice", last_name="A")
    bob = setup_author(email="bob@x.com", code="E-BOB", proj_code="P-BOB", first_name="Bob", last_name="B")
    _, fmtl = _make_sub_activity(
        client, activity_admin, benchmark_type="NUMERIC", benchmark_value=250,
        relevant_count_field="tags", name="FMTL Rework",
    )
    _, audit = _make_sub_activity(client, activity_admin, benchmark_type="TASK_BASED", name="Audit Query")

    for actor, count in ((alice, 200), (bob, 100)):
        payload = {
            "report_date": TODAY,
            "tasks": [{
                "project_id": str(actor["project"].id), "description": "work",
                "sub_activity_id": fmtl["id"], "tags_count": count,
            }],
        }
        created = client.post(BASE, headers=actor["header"], json=payload).json()
        client.post(f"{BASE}/{created['id']}/submit", headers=actor["header"])

    total_target = 250 * 2  # one reported day each, two employees
    expected_productivity = (200 + 100) / total_target * 100

    body = client.get(ALERTS_BASE + "/team-alerts", headers=activity_admin).json()
    # One reported row per employee today — no synthesized rows for the
    # other elapsed weekdays.
    assert len(body["backlog"]) == 2
    names = {row["employee_name"] for row in body["backlog"]}
    assert names == {alice["emp"].full_name, bob["emp"].full_name}
    today_rows = [r for r in body["backlog"] if r["date"] == TODAY]
    assert len(today_rows) == 2
    assert {float(r["actual"]) for r in today_rows} == {200.0, 100.0}
    assert body["kpis"]["total_pending_benchmarks"] == 2
    assert body["kpis"]["total_employees"] >= 2
    # weighted: (200+100) actual over (250 * 2 employees) target, not a
    # plain average of each employee's productivity_pct.
    assert float(body["kpis"]["weekly_productivity_pct"]) == pytest.approx(expected_productivity)
    assert body["kpis"]["total_overdue_activities"] == 0
