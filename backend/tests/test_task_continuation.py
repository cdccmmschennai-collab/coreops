"""Task continuation (work_items) — due-date rule, create/continue/complete,
editing, reader deduplication, backward compatibility, and the migration shape.

The feature is behind settings.TASK_CONTINUATION_ENABLED (default OFF). The
`flag_on` fixture flips the singleton for the duration of a test; tests that omit
it exercise the legacy path, proving disabled == old behaviour.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.modules.activity_master.service import (
    compute_week_bounds,
    get_cycle_task_activities,
    get_overdue_activities,
    get_task_status_activities,
)
from app.modules.benchmarks.service import get_pending_benchmark_export
from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole
from app.modules.work_reports.models import WorkItem
from app.modules.work_reports.work_items import compute_due_date
from app.shared.errors import AppError

BASE = "/api/v1/work-reports"
OPEN_TASKS = "/api/v1/work-reports/open-tasks"
TODAY = date.today()


# --------------------------------------------------------------------------
# fixtures / helpers
# --------------------------------------------------------------------------
@pytest.fixture()
def flag_on():
    prev = settings.TASK_CONTINUATION_ENABLED
    settings.TASK_CONTINUATION_ENABLED = True
    try:
        yield
    finally:
        settings.TASK_CONTINUATION_ENABLED = prev


@pytest.fixture()
def author(make_user, make_employee, make_project, make_project_member, login):
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


def _task_sub(client, admin, *, name="Lumpsum", period=2, count_field=None, value=None):
    """A TASK_BASED sub-activity. count_field/value make it count-based (CASE A)."""
    a = client.post(
        "/api/v1/activity-master/activities",
        json={"name": f"Activity {name}"}, headers=admin,
    ).json()
    body = {"name": name, "benchmark_type": "TASK_BASED"}
    if count_field:
        body["relevant_count_field"] = count_field
        body["benchmark_value"] = value
    sub = client.post(
        f"/api/v1/activity-master/activities/{a['id']}/sub-activities",
        json=body, headers=admin,
    ).json()
    client.patch(
        f"/api/v1/activity-master/sub-activities/{sub['id']}",
        json={"benchmark_period_days": period}, headers=admin,
    )
    return a, sub


def _post_report(client, header, *, project_id, sub_id, on_date, work_item_id=None,
                 is_completed=False, tags=0, expect=201):
    task = {
        "project_id": str(project_id), "description": "work",
        "sub_activity_id": sub_id, "is_completed": is_completed, "tags_count": tags,
    }
    if work_item_id is not None:
        task["work_item_id"] = str(work_item_id)
    res = client.post(BASE, headers=header, json={
        "report_date": on_date.isoformat(), "day_status": "work_at_office",
        "location": "chennai", "tasks": [task],
    })
    assert res.status_code == expect, res.text
    return res


def _get_report(client, header, report_id):
    res = client.get(f"{BASE}/{report_id}", headers=header)
    assert res.status_code == 200, res.text
    return res.json()


# --------------------------------------------------------------------------
# due-date rule (pure)
# --------------------------------------------------------------------------
def test_due_date_one_day():
    assert compute_due_date(date(2026, 7, 10), 1) == date(2026, 7, 10)


def test_due_date_two_days():
    assert compute_due_date(date(2026, 7, 10), 2) == date(2026, 7, 11)


def test_due_date_three_days():
    assert compute_due_date(date(2026, 7, 10), 3) == date(2026, 7, 12)


def test_due_date_includes_weekend():
    # Fri 2026-07-10 + 3 calendar days spans the weekend -> Sun 2026-07-12.
    assert date(2026, 7, 10).weekday() == 4  # Friday
    assert compute_due_date(date(2026, 7, 10), 3) == date(2026, 7, 12)
    assert compute_due_date(date(2026, 7, 10), 3).weekday() == 6  # Sunday


def test_due_date_target_days_clamped_to_one():
    # A zero/blank period must never push the deadline before the start.
    assert compute_due_date(date(2026, 7, 10), 0) == date(2026, 7, 10)


def test_due_date_matches_frontend_preview():
    # Frontend preview is addDays(reportDate, periodDays - 1); assert the shared
    # arithmetic so the one-line UI preview and the server agree.
    start = date(2026, 7, 10)
    for period in (1, 2, 3, 5):
        js_preview = start + timedelta(days=period - 1)
        assert compute_due_date(start, period) == js_preview


def test_work_items_target_days_zero_rejected(db, author):
    a = author()
    from app.modules.activity_master.models import (
        LEVEL_ACTIVITY,
        LEVEL_SUB_ACTIVITY,
        ActivityMaster,
    )
    act = ActivityMaster(name="A", level=LEVEL_ACTIVITY)
    db.add(act)
    db.flush()
    sub = ActivityMaster(
        name="S", level=LEVEL_SUB_ACTIVITY, parent_id=act.id,
        benchmark_type="TASK_BASED", benchmark_period_days=2,
    )
    db.add(sub)
    db.flush()
    # Direct insert with target_days = 0 must violate the check constraint even
    # with otherwise-valid FKs.
    db.add(WorkItem(
        employee_id=a["emp"].id, project_id=a["project"].id,
        sub_activity_id=sub.id, started_on=TODAY, target_days=0, due_date=TODAY,
    ))
    with pytest.raises(Exception):
        db.commit()
    db.rollback()


# --------------------------------------------------------------------------
# creation & continuation
# --------------------------------------------------------------------------
def test_start_creates_one_work_item(flag_on, client, author, pm_header, db):
    a = author()
    _, sub = _task_sub(client, pm_header, period=2)
    r = _post_report(client, a["header"], project_id=a["project"].id,
                     sub_id=sub["id"], on_date=TODAY).json()
    assert r["tasks"][0]["work_item_id"] is not None
    assert r["tasks"][0]["due_date"] == (TODAY + timedelta(days=1)).isoformat()
    assert db.query(WorkItem).count() == 1


def test_continuation_full_flow(flag_on, client, author, pm_header, db):
    a = author()
    _, sub = _task_sub(client, pm_header, period=3)
    start = TODAY - timedelta(days=4)
    r1 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=start).json()
    wid = r1["tasks"][0]["work_item_id"]
    due = r1["tasks"][0]["due_date"]
    assert due == (start + timedelta(days=2)).isoformat()

    # Open-tasks for a later, non-sequential date lists the item.
    later = TODAY - timedelta(days=1)
    ot = client.get(OPEN_TASKS, headers=a["header"],
                    params={"report_date": later.isoformat()}).json()
    assert [t["work_item_id"] for t in ot["items"]] == [wid]

    # Continue on the later date -> same item, unchanged started_on/due_date.
    r2 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=later, work_item_id=wid).json()
    assert r2["tasks"][0]["work_item_id"] == wid
    assert r2["tasks"][0]["due_date"] == due
    assert r2["tasks"][0]["started_date"] == start.isoformat()
    assert db.query(WorkItem).count() == 1
    item = db.query(WorkItem).one()
    assert item.started_on == start
    assert item.due_date == start + timedelta(days=2)


def test_overdue_task_can_be_continued(flag_on, client, author, pm_header, db):
    a = author()
    _, sub = _task_sub(client, pm_header, period=1)  # due = start
    start = TODAY - timedelta(days=3)  # already overdue
    r1 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=start).json()
    wid = r1["tasks"][0]["work_item_id"]
    # Still listed (overdue) and still continuable.
    ot = client.get(OPEN_TASKS, headers=a["header"],
                    params={"report_date": TODAY.isoformat()}).json()
    assert ot["items"][0]["lifecycle"] == "OVERDUE"
    assert ot["items"][0]["days_overdue"] == 3
    _post_report(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=TODAY, work_item_id=wid)
    assert db.query(WorkItem).count() == 1


def test_start_new_creates_separate_item(flag_on, client, author, pm_header, db):
    a = author()
    _, sub = _task_sub(client, pm_header, period=2)
    _post_report(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=TODAY - timedelta(days=2))
    # Second report, SAME sub, no work_item_id -> explicit start-new.
    _post_report(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=TODAY)
    assert db.query(WorkItem).count() == 2


def test_other_employee_cannot_continue(flag_on, client, author, pm_header, db):
    a = author(email="a@x.com", code="E-1", proj_code="P-1")
    b = author(email="b@x.com", code="E-2", proj_code="P-2")
    _, sub = _task_sub(client, pm_header, period=2)
    r1 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=TODAY).json()
    wid = r1["tasks"][0]["work_item_id"]
    # B is on a different project; even matching it, ownership blocks first.
    _post_report(client, b["header"], project_id=b["project"].id,
                 sub_id=sub["id"], on_date=TODAY, work_item_id=wid, expect=403)


def test_mismatched_sub_activity_rejected(flag_on, client, author, pm_header):
    a = author()
    _, sub1 = _task_sub(client, pm_header, name="One", period=2)
    _, sub2 = _task_sub(client, pm_header, name="Two", period=2)
    r1 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub1["id"], on_date=TODAY - timedelta(days=1)).json()
    wid = r1["tasks"][0]["work_item_id"]
    # Continue on a later date but point at a different sub-activity -> 422.
    _post_report(client, a["header"], project_id=a["project"].id,
                 sub_id=sub2["id"], on_date=TODAY, work_item_id=wid, expect=422)


def test_report_date_before_start_rejected(flag_on, client, author, pm_header):
    a = author()
    _, sub = _task_sub(client, pm_header, period=2)
    start = TODAY - timedelta(days=1)
    r1 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=start).json()
    wid = r1["tasks"][0]["work_item_id"]
    # Continue on a date BEFORE the task started -> 422.
    _post_report(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=start - timedelta(days=2),
                 work_item_id=wid, expect=422)


def test_duplicate_work_item_in_one_report_rejected(flag_on, client, author, pm_header, db):
    a = author()
    _, sub = _task_sub(client, pm_header, period=2)
    r1 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=TODAY - timedelta(days=1)).json()
    wid = r1["tasks"][0]["work_item_id"]
    # A single report continuing the same work item twice -> 422, and rollback
    # leaves no stray work item (still exactly the one).
    res = client.post(BASE, headers=a["header"], json={
        "report_date": TODAY.isoformat(), "day_status": "work_at_office",
        "location": "chennai",
        "tasks": [
            {"project_id": str(a["project"].id), "description": "x",
             "sub_activity_id": sub["id"], "work_item_id": str(wid)},
            {"project_id": str(a["project"].id), "description": "y",
             "sub_activity_id": sub["id"], "work_item_id": str(wid)},
        ],
    })
    assert res.status_code == 422, res.text
    assert db.query(WorkItem).count() == 1


def test_failed_create_rolls_back_work_item(flag_on, client, author, pm_header, db):
    """A START row followed by a duplicate-link failure must leave NO work item."""
    a = author()
    _, sub = _task_sub(client, pm_header, period=2)
    r1 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=TODAY - timedelta(days=1)).json()
    wid = r1["tasks"][0]["work_item_id"]
    before = db.query(WorkItem).count()
    res = client.post(BASE, headers=a["header"], json={
        "report_date": TODAY.isoformat(), "day_status": "work_at_office",
        "location": "chennai",
        "tasks": [
            # a fresh START (would create an item) ...
            {"project_id": str(a["project"].id), "description": "new",
             "sub_activity_id": sub["id"]},
            # ... then a duplicate continuation that aborts the whole request.
            {"project_id": str(a["project"].id), "description": "dup",
             "sub_activity_id": sub["id"], "work_item_id": str(wid)},
            {"project_id": str(a["project"].id), "description": "dup2",
             "sub_activity_id": sub["id"], "work_item_id": str(wid)},
        ],
    })
    assert res.status_code == 422, res.text
    assert db.query(WorkItem).count() == before  # the START item rolled back too


# --------------------------------------------------------------------------
# completion
# --------------------------------------------------------------------------
def _complete_via_endpoint(client, header, task_id, is_completed=True, expect=200):
    res = client.patch(f"{BASE}/tasks/{task_id}/completion", headers=header,
                       json={"is_completed": is_completed})
    assert res.status_code == expect, res.text
    return res


def test_completed_before_due_is_on_time(flag_on, client, author, pm_header):
    a = author()
    _, sub = _task_sub(client, pm_header, period=3)  # due = start + 2
    r = _post_report(client, a["header"], project_id=a["project"].id,
                     sub_id=sub["id"], on_date=TODAY, is_completed=True).json()
    assert r["tasks"][0]["work_item_lifecycle"] == "COMPLETED_ON_TIME"


def test_completed_on_due_date_is_on_time(flag_on, client, author, pm_header):
    a = author()
    _, sub = _task_sub(client, pm_header, period=3)
    start = TODAY - timedelta(days=2)  # due == today
    r1 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=start).json()
    tid = r1["tasks"][0]["id"]
    res = _complete_via_endpoint(client, a["header"], tid).json()
    assert res["work_item_lifecycle"] == "COMPLETED_ON_TIME"


def test_completed_after_due_is_late(flag_on, client, author, pm_header):
    a = author()
    _, sub = _task_sub(client, pm_header, period=1)  # due == start
    start = TODAY - timedelta(days=3)
    r1 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=start).json()
    wid = r1["tasks"][0]["work_item_id"]
    # Continue on a later report (dated after the due date) and complete THERE,
    # so completed_on (that report's date) > due_date -> COMPLETED_LATE.
    r2 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=TODAY, work_item_id=wid).json()
    res = _complete_via_endpoint(client, a["header"], r2["tasks"][0]["id"]).json()
    assert res["work_item_lifecycle"] == "COMPLETED_LATE"


def test_completed_task_cannot_be_continued(flag_on, client, author, pm_header):
    a = author()
    _, sub = _task_sub(client, pm_header, period=3)
    start = TODAY - timedelta(days=1)
    r1 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=start, is_completed=True).json()
    wid = r1["tasks"][0]["work_item_id"]
    _post_report(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=TODAY, work_item_id=wid, expect=422)


def test_submitted_completed_cannot_be_reopened(flag_on, client, author, pm_header):
    a = author()
    _, sub = _task_sub(client, pm_header, period=3)
    # Complete while the report is still a draft (the new model completes on the
    # editable report), then submit -> completion is frozen read-only.
    r1 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=TODAY, is_completed=True).json()
    tid = r1["tasks"][0]["id"]
    client.post(f"{BASE}/{r1['id']}/submit", headers=a["header"])
    _complete_via_endpoint(client, a["header"], tid, is_completed=False, expect=422)


def test_cannot_complete_on_submitted_report(flag_on, client, author, pm_header):
    """A submitted (non-editable) report cannot complete an open task via PATCH —
    completion is read-only once submitted (new control rule)."""
    a = author()
    _, sub = _task_sub(client, pm_header, period=3)
    r1 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=TODAY).json()
    tid = r1["tasks"][0]["id"]
    client.post(f"{BASE}/{r1['id']}/submit", headers=a["header"])
    _complete_via_endpoint(client, a["header"], tid, is_completed=True, expect=422)


def test_draft_completion_can_be_corrected(flag_on, client, author, pm_header, db):
    a = author()
    _, sub = _task_sub(client, pm_header, period=3)
    r1 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=TODAY, is_completed=True).json()
    wid = r1["tasks"][0]["work_item_id"]
    assert db.get(WorkItem, wid).completed_on is not None
    # Edit the still-draft report, unticking completion -> reopened.
    res = client.patch(f"{BASE}/{r1['id']}", headers=a["header"], json={
        "tasks": [{"project_id": str(a["project"].id), "description": "work",
                   "sub_activity_id": sub["id"], "work_item_id": str(wid),
                   "is_completed": False}],
    })
    assert res.status_code == 200, res.text
    db.expire_all()
    assert db.get(WorkItem, wid).completed_on is None


# --------------------------------------------------------------------------
# editing (delete-recreate)
# --------------------------------------------------------------------------
def test_resave_preserves_link_and_no_duplicate_item(flag_on, client, author, pm_header, db):
    a = author()
    _, sub = _task_sub(client, pm_header, period=2)
    r1 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=TODAY).json()
    wid = r1["tasks"][0]["work_item_id"]
    # Re-save (edit remarks) carrying the same work_item_id back.
    res = client.patch(f"{BASE}/{r1['id']}", headers=a["header"], json={
        "remarks": "edited",
        "tasks": [{"project_id": str(a["project"].id), "description": "work",
                   "sub_activity_id": sub["id"], "work_item_id": str(wid)}],
    })
    assert res.status_code == 200, res.text
    assert res.json()["tasks"][0]["work_item_id"] == wid
    assert db.query(WorkItem).count() == 1


def test_cannot_behead_started_item_with_continuations(flag_on, client, author, pm_header):
    a = author()
    _, sub = _task_sub(client, pm_header, period=3)
    start = TODAY - timedelta(days=2)
    r1 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=start).json()
    wid = r1["tasks"][0]["work_item_id"]
    _post_report(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=TODAY, work_item_id=wid)
    # Remove the originating task from R1 (switch it to a leave day) -> blocked.
    res = client.patch(f"{BASE}/{r1['id']}", headers=a["header"],
                       json={"day_status": "leave", "tasks": []})
    assert res.status_code == 422, res.text


def test_continuation_row_removal_keeps_item(flag_on, client, author, pm_header, db):
    a = author()
    _, sub = _task_sub(client, pm_header, period=3)
    start = TODAY - timedelta(days=2)
    r1 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=start).json()
    wid = r1["tasks"][0]["work_item_id"]
    r2 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=TODAY, work_item_id=wid).json()
    # Drop the continuation entry (R2) -> allowed; item + origin survive.
    res = client.patch(f"{BASE}/{r2['id']}", headers=a["header"],
                       json={"day_status": "leave", "tasks": []})
    assert res.status_code == 200, res.text
    assert db.get(WorkItem, wid) is not None


def test_delete_originating_draft_with_continuations_blocked(flag_on, client, author, pm_header):
    a = author()
    _, sub = _task_sub(client, pm_header, period=3)
    start = TODAY - timedelta(days=2)
    r1 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=start).json()
    wid = r1["tasks"][0]["work_item_id"]
    _post_report(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=TODAY, work_item_id=wid)
    res = client.delete(f"{BASE}/{r1['id']}", headers=a["header"])
    assert res.status_code == 422, res.text


def test_delete_lone_draft_cleans_up_item(flag_on, client, author, pm_header, db):
    a = author()
    _, sub = _task_sub(client, pm_header, period=2)
    r1 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=TODAY).json()
    assert db.query(WorkItem).count() == 1
    res = client.delete(f"{BASE}/{r1['id']}", headers=a["header"])
    assert res.status_code == 204, res.text
    db.expire_all()
    assert db.query(WorkItem).count() == 0  # orphan cleaned up, not left behind


# --------------------------------------------------------------------------
# reader deduplication
# --------------------------------------------------------------------------
def test_readers_collapse_three_entries_to_one(flag_on, client, author, pm_header, db):
    a = author()
    # period=1 (due == start) so the item is overdue when the export runs a few
    # days later — that's the export's inclusion trigger. Count-based (tags/1000)
    # so it participates in the numeric totals.
    _, sub = _task_sub(client, pm_header, name="Count", period=1,
                       count_field="tags", value=1000)
    # Use the PREVIOUS cycle so all three dates are firmly in the past
    # regardless of which weekday the suite runs on.
    week_start = compute_week_bounds(TODAY)[0] - timedelta(days=7)
    d0, d1, d2 = week_start, week_start + timedelta(days=1), week_start + timedelta(days=2)
    r0 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=d0, tags=100).json()
    wid = r0["tasks"][0]["work_item_id"]
    for d in (d1, d2):
        _post_report(client, a["header"], project_id=a["project"].id,
                     sub_id=sub["id"], on_date=d, work_item_id=wid, tags=100)

    eid = {a["emp"].id}
    cyc = get_cycle_task_activities(db, employee_ids=eid, today=d0)
    mine = [r for r in cyc if str(r["work_item_id"]) == wid]
    assert len(mine) == 1                       # one logical result, not three
    assert mine[0]["actual"] == 300             # counts summed across entries

    status = get_task_status_activities(db, employee_ids=eid, today=d0)
    assert len([r for r in status if str(r["work_item_id"]) == wid]) == 1

    # Evaluate the export a few days later so the due (d0) is past -> included.
    export = get_pending_benchmark_export(db, cycle="current", today=d0 + timedelta(days=3))
    detail = [r for r in export["rows"] if r["sub_activity"] == "Count"]
    assert len(detail) == 1                     # one export row for the work item


def test_overdue_reader_dedupes(flag_on, client, author, pm_header, db):
    a = author()
    _, sub = _task_sub(client, pm_header, period=1)  # due == start
    d0 = compute_week_bounds(TODAY)[0] - timedelta(days=7)  # previous cycle Friday
    r0 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=d0).json()
    wid = r0["tasks"][0]["work_item_id"]
    _post_report(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=d0 + timedelta(days=1), work_item_id=wid)
    # Evaluate "today" three days later so due (d0) is in-cycle and past.
    overdue = get_overdue_activities(db, employee_ids={a["emp"].id},
                                     today=d0 + timedelta(days=3))
    assert len([r for r in overdue if str(r["work_item_id"]) == wid]) == 1


def test_completing_on_continuation_day_clears_earlier_benchmark(
    flag_on, client, author, pm_header, db
):
    """Regression: completing a task on a LATER continuation day (via the report
    FORM, not the completion endpoint) must clear the earlier day's benchmark
    from every reader. The originating row's mirrored is_completed stays stale by
    design ('benchmark only') — the readers derive completion from the
    authoritative work item, so the whole item drops out regardless."""
    import uuid as _uuid

    a = author()
    _, sub = _task_sub(client, pm_header, name="Cont", period=1,   # due == start
                       count_field="tags", value=1000)
    d0 = compute_week_bounds(TODAY)[0] - timedelta(days=7)         # prev-cycle Friday
    d1 = d0 + timedelta(days=1)
    r0 = _post_report(client, a["header"], project_id=a["project"].id,
                      sub_id=sub["id"], on_date=d0, tags=100).json()
    wid = r0["tasks"][0]["work_item_id"]
    # Continue on d1 and tick "complete" on the FORM (is_completed=True), which is
    # the create/update path — NOT the PATCH completion endpoint.
    _post_report(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=d1, work_item_id=wid,
                 is_completed=True, tags=100)

    # Work item is authoritatively completed on d1; the d0 row's flag stays stale.
    item = db.get(WorkItem, _uuid.UUID(wid))
    assert item.completed_on == d1
    d0_row_completed = db.execute(text(
        "SELECT t.is_completed FROM work_report_tasks t "
        "JOIN daily_work_reports r ON r.id = t.report_id "
        "WHERE t.work_item_id = :w AND r.report_date = :d"
    ), {"w": wid, "d": d0}).scalar()
    assert d0_row_completed is False                     # stale by design

    eid = {a["emp"].id}
    today = d0 + timedelta(days=3)                       # due (d0) now past & in-cycle
    # Overdue reader: the completed item must NOT appear (the bug: it did).
    overdue = get_overdue_activities(db, employee_ids=eid, today=today)
    assert [r for r in overdue if str(r["work_item_id"]) == wid] == []
    # Task-status reader: present once, marked completed rather than pending.
    status = [r for r in get_task_status_activities(db, employee_ids=eid, today=today)
              if str(r["work_item_id"]) == wid]
    assert len(status) == 1 and status[0]["status"] == "completed"
    # Cycle reader (pending-export source): completion is authoritative.
    cyc = [r for r in get_cycle_task_activities(db, employee_ids=eid, today=today)
           if str(r["work_item_id"]) == wid]
    assert len(cyc) == 1 and cyc[0]["is_completed"] is True


# --------------------------------------------------------------------------
# daily-row vs overall-task completion semantics
# --------------------------------------------------------------------------
def test_start_10_complete_on_11_separates_daily_and_overall(
    flag_on, client, author, pm_header, db
):
    """Scenario 1: start 10 July, complete via the 11 July continuation form."""
    a = author()
    _, sub = _task_sub(client, pm_header, period=1)      # due == start
    d10 = TODAY - timedelta(days=1)
    d11 = TODAY
    r10 = _post_report(client, a["header"], project_id=a["project"].id,
                       sub_id=sub["id"], on_date=d10).json()
    wid = r10["tasks"][0]["work_item_id"]
    r11 = _post_report(client, a["header"], project_id=a["project"].id,
                       sub_id=sub["id"], on_date=d11, work_item_id=wid,
                       is_completed=True).json()

    # 11 July completion row.
    t11 = r11["tasks"][0]
    assert t11["row_is_completed"] is True
    assert t11["row_completed_date"] == d11.isoformat()
    assert t11["completed_on_this_report"] is True
    assert t11["overall_completed_on"] == d11.isoformat()
    assert t11["overall_lifecycle"] == "COMPLETED_LATE"    # completed d11 > due d10
    assert t11["can_complete_here"] is False               # already completed

    # 10 July originating row — completion lives on the 11 July report.
    t10 = _get_report(client, a["header"], r10["id"])["tasks"][0]
    assert t10["row_is_completed"] is False
    assert t10["row_completed_date"] is None
    assert t10["completed_on_this_report"] is False
    assert t10["overall_completed_on"] == d11.isoformat()
    assert t10["overall_lifecycle"] == "COMPLETED_LATE"
    assert t10["completion_report_id"] == r11["id"]        # link to where completed
    assert t10["can_complete_here"] is False               # NO active control here


def test_completed_item_cannot_be_backdated_from_earlier_report(
    flag_on, client, author, pm_header, db
):
    """Scenario 2: once completed on a later report, an earlier report cannot
    re-complete / backdate the overall completion."""
    import uuid as _uuid

    a = author()
    _, sub = _task_sub(client, pm_header, period=3)
    d10 = TODAY - timedelta(days=1)
    r10 = _post_report(client, a["header"], project_id=a["project"].id,
                       sub_id=sub["id"], on_date=d10).json()
    wid = r10["tasks"][0]["work_item_id"]
    tid10 = r10["tasks"][0]["id"]
    _post_report(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=TODAY, work_item_id=wid,
                 is_completed=True)
    # PATCH-completing the (still editable) 10 July draft is rejected.
    _complete_via_endpoint(client, a["header"], tid10, is_completed=True, expect=422)
    assert db.get(WorkItem, _uuid.UUID(wid)).completed_on == TODAY


def test_submitted_completion_is_read_only_in_output(
    flag_on, client, author, pm_header
):
    """Scenario 3: a submitted report exposes no active completion control."""
    a = author()
    _, sub = _task_sub(client, pm_header, period=3)
    r = _post_report(client, a["header"], project_id=a["project"].id,
                     sub_id=sub["id"], on_date=TODAY).json()
    client.post(f"{BASE}/{r['id']}/submit", headers=a["header"])
    t = _get_report(client, a["header"], r["id"])["tasks"][0]
    assert t["can_complete_here"] is False


def test_open_task_completed_via_current_continuation(
    flag_on, client, author, pm_header, db
):
    """Scenario 4: an open task is completable on the latest continuation, not on
    an earlier entry."""
    import uuid as _uuid

    a = author()
    _, sub = _task_sub(client, pm_header, period=3)
    d10 = TODAY - timedelta(days=1)
    r10 = _post_report(client, a["header"], project_id=a["project"].id,
                       sub_id=sub["id"], on_date=d10).json()
    wid = r10["tasks"][0]["work_item_id"]
    r11 = _post_report(client, a["header"], project_id=a["project"].id,
                       sub_id=sub["id"], on_date=TODAY, work_item_id=wid).json()
    t11 = r11["tasks"][0]
    assert t11["can_complete_here"] is True                # latest, editable, open
    t10 = _get_report(client, a["header"], r10["id"])["tasks"][0]
    assert t10["can_complete_here"] is False               # not the latest entry

    res = _complete_via_endpoint(client, a["header"], t11["id"]).json()
    assert res["completed_on_this_report"] is True
    assert res["overall_completed_on"] == TODAY.isoformat()
    assert db.get(WorkItem, _uuid.UUID(wid)).completed_on == TODAY


def test_patch_and_form_completion_produce_identical_state(
    flag_on, client, author, pm_header
):
    """Scenario 5: form-save completion and PATCH completion yield identical row
    and work-item state."""
    def build(email, code, pcode, *, via):
        a = author(email=email, code=code, proj_code=pcode)
        _, sub = _task_sub(client, pm_header, name=code, period=1)
        d0 = TODAY - timedelta(days=1)
        r0 = _post_report(client, a["header"], project_id=a["project"].id,
                          sub_id=sub["id"], on_date=d0).json()
        wid = r0["tasks"][0]["work_item_id"]
        if via == "form":
            r1 = _post_report(client, a["header"], project_id=a["project"].id,
                              sub_id=sub["id"], on_date=TODAY, work_item_id=wid,
                              is_completed=True).json()
        else:
            r1 = _post_report(client, a["header"], project_id=a["project"].id,
                              sub_id=sub["id"], on_date=TODAY, work_item_id=wid).json()
            _complete_via_endpoint(client, a["header"], r1["tasks"][0]["id"])
            r1 = _get_report(client, a["header"], r1["id"])
        t0 = _get_report(client, a["header"], r0["id"])["tasks"][0]
        t1 = r1["tasks"][0]
        return (
            t0["row_is_completed"], t0["completed_on_this_report"],
            t0["overall_completed_on"], t0["completion_report_id"] == r1["id"],
            t1["row_is_completed"], t1["completed_on_this_report"],
            t1["overall_completed_on"],
        )

    form_state = build("f@x.com", "F-1", "PF-1", via="form")
    patch_state = build("p@x.com", "P-1", "PP-1", via="patch")
    assert form_state == patch_state
    # Concrete expected shape: d0 open, TODAY the completion row.
    assert form_state == (False, False, TODAY.isoformat(), True,
                          True, True, TODAY.isoformat())


# --------------------------------------------------------------------------
# backward compatibility (flag OFF) + NUMERIC untouched
# --------------------------------------------------------------------------
def test_legacy_row_completion_unchanged(client, author, pm_header):
    """Scenario 6: with the flag OFF a TASK_BASED row has no work item and the
    PATCH endpoint toggles just that row, even after submit (legacy bypass)."""
    a = author()
    _, sub = _task_sub(client, pm_header, period=2)
    r = _post_report(client, a["header"], project_id=a["project"].id,
                     sub_id=sub["id"], on_date=TODAY).json()
    t = r["tasks"][0]
    assert t["work_item_id"] is None
    assert t["can_complete_here"] is None            # not a work-item-gated row
    tid = t["id"]
    client.post(f"{BASE}/{r['id']}/submit", headers=a["header"])
    res = _complete_via_endpoint(client, a["header"], tid, is_completed=True).json()
    assert res["row_is_completed"] is True
    assert res["overall_completed_on"] is None       # no work item
    res2 = _complete_via_endpoint(client, a["header"], tid, is_completed=False).json()
    assert res2["row_is_completed"] is False



def test_flag_off_creates_no_work_item(client, author, pm_header, db):
    a = author()
    _, sub = _task_sub(client, pm_header, period=2)
    r = _post_report(client, a["header"], project_id=a["project"].id,
                     sub_id=sub["id"], on_date=TODAY).json()
    assert r["tasks"][0]["work_item_id"] is None
    # Legacy per-row dates still stamped.
    assert r["tasks"][0]["due_date"] == (TODAY + timedelta(days=1)).isoformat()
    assert db.query(WorkItem).count() == 0
    # No open-tasks surfaced while disabled.
    ot = client.get(OPEN_TASKS, headers=a["header"],
                    params={"report_date": TODAY.isoformat()}).json()
    assert ot["items"] == []


def test_numeric_benchmark_never_creates_work_item(flag_on, client, author, pm_header, db):
    a = author()
    aa = client.post("/api/v1/activity-master/activities",
                     json={"name": "Numeric A"}, headers=pm_header).json()
    sub = client.post(
        f"/api/v1/activity-master/activities/{aa['id']}/sub-activities",
        json={"name": "Nums", "benchmark_type": "NUMERIC",
              "benchmark_value": 100, "relevant_count_field": "tags"},
        headers=pm_header,
    ).json()
    r = _post_report(client, a["header"], project_id=a["project"].id,
                     sub_id=sub["id"], on_date=TODAY, tags=40).json()
    assert r["tasks"][0]["work_item_id"] is None
    assert db.query(WorkItem).count() == 0


# --------------------------------------------------------------------------
# migration shape
# --------------------------------------------------------------------------
def test_migration_shape(db):
    # work_items table exists with the nullable-completion + constraints.
    cols = db.execute(text(
        "SELECT column_name, is_nullable FROM information_schema.columns "
        "WHERE table_name = 'work_items'"
    )).all()
    names = {c[0] for c in cols}
    assert {"started_on", "target_days", "due_date", "completed_on"} <= names
    # work_report_tasks.work_item_id exists and is nullable.
    wi_col = db.execute(text(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name = 'work_report_tasks' AND column_name = 'work_item_id'"
    )).scalar_one()
    assert wi_col == "YES"
