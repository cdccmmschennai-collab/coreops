"""Lump-sum Activity Continuation Approval (Phase 2).

Covers: gate blocking/allowing continuation, request creation + duplicate
prevention, Head resolution + reassignment, PM (line-manager) fallback,
approve/reject, unauthorized/self-approval, notifications, and non-regression
of TASK_WITH_QUANTITY continuation and existing work-item behaviour.
"""
from datetime import date, timedelta

import pytest

from app.core.config import settings
from app.modules.continuation_requests.models import ContinuationRequest
from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole

BASE = "/api/v1/work-reports"
OPEN_TASKS = "/api/v1/work-reports/open-tasks"
CR = "/api/v1/continuation-requests"
TODAY = date.today()
# Work items are started in the PAST and continued on TODAY: a report cannot be
# dated in the future, so the "continue it later" leg has to be today and the
# start has to be behind it. A 1-day lump-sum started on START (due = START,
# since add_working_days(start, 0) is start itself) is always overdue by TODAY.
START = TODAY - timedelta(days=3)


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
    def _make(*, email="emp@x.com", code="E-1", proj_code="P-1", manager_id=None, head_id=None):
        u = make_user(email, role=UserRole.employee)
        e = make_employee(employee_code=code, user_id=u.id, manager_id=manager_id)
        p = make_project(code=proj_code, status=ProjectStatus.active, head_employee_id=head_id)
        make_project_member(project_id=p.id, employee_id=e.id)
        return {"user": u, "emp": e, "project": p, "header": login(email)}

    return _make


@pytest.fixture()
def pm_header(auth_header):
    return auth_header(email="pm@x.com", role=UserRole.project_manager)


def _lumpsum_sub(client, admin, *, name="Lumpsum", period=1):
    a = client.post(
        "/api/v1/activity-master/activities", json={"name": f"Activity {name}"}, headers=admin,
    ).json()
    sub = client.post(
        f"/api/v1/activity-master/activities/{a['id']}/sub-activities",
        json={"name": name, "benchmark_type": "TASK_STATUS_ONLY"}, headers=admin,
    ).json()
    client.patch(
        f"/api/v1/activity-master/sub-activities/{sub['id']}",
        json={"benchmark_period_days": period}, headers=admin,
    )
    return a, sub


def _quantity_task_sub(client, admin, *, name="Quantity", period=1):
    a = client.post(
        "/api/v1/activity-master/activities", json={"name": f"Activity {name}"}, headers=admin,
    ).json()
    sub = client.post(
        f"/api/v1/activity-master/activities/{a['id']}/sub-activities",
        json={"name": name, "benchmark_type": "TASK_WITH_QUANTITY",
              "relevant_count_field": "pages", "benchmark_value": 100,
              "benchmark_period_days": period},
        headers=admin,
    ).json()
    return a, sub


def _post_report(client, header, *, project_id, sub_id, on_date, work_item_id=None, expect=201):
    task = {"project_id": str(project_id), "description": "work", "sub_activity_id": sub_id}
    if work_item_id is not None:
        task["work_item_id"] = str(work_item_id)
    res = client.post(BASE, headers=header, json={
        "report_date": on_date.isoformat(), "day_status": "work_at_office",
        "location": "chennai", "tasks": [task],
    })
    assert res.status_code == expect, res.text
    return res


def _start_work_item(client, header, *, project_id, sub_id, on_date):
    r = _post_report(client, header, project_id=project_id, sub_id=sub_id, on_date=on_date).json()
    return r["tasks"][0]["work_item_id"]


# --------------------------------------------------------------------------
# 1/2/3: within-duration continues; overdue lump-sum is blocked; approval unblocks
# --------------------------------------------------------------------------

def test_within_duration_continues_normally(flag_on, client, author, pm_header):
    a = author()
    # 6-day duration = START + 5 WORKING days, which is at least 5 calendar
    # days out - comfortably past TODAY (START is 3 days back) whatever weekday
    # START lands on, so this continuation is still within the allowed duration.
    _, sub = _lumpsum_sub(client, pm_header, period=6)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY
    _post_report(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                 on_date=cont_day, work_item_id=wi, expect=201)


def test_overdue_lumpsum_continuation_auto_requests_and_saves(
    flag_on, client, db, author, pm_header, make_user, make_employee, login,
):
    """The employee can always continue an overdue lump-sum item in today's
    report: the save succeeds, and a pending ContinuationRequest is
    auto-created behind the scenes (same table/dedup rule/notification the
    explicit endpoint uses) instead of hard-blocking the save."""
    from sqlalchemy import select

    from app.modules.notifications.models import Notification

    head_u = make_user("head6@x.com", role=UserRole.employee)
    head = make_employee(employee_code="H6", user_id=head_u.id)
    a = author(email="emp6@x.com", code="E6", proj_code="P-6", head_id=head.id)

    _, sub = _lumpsum_sub(client, pm_header, period=1)  # due the same day it starts
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY
    res = _post_report(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                       on_date=cont_day, work_item_id=wi, expect=201)
    assert res.json()["tasks"][0]["work_item_id"] == wi

    reqs = db.execute(
        select(ContinuationRequest).where(ContinuationRequest.work_item_id == wi)
    ).scalars().all()
    assert len(reqs) == 1
    assert reqs[0].status == "pending"
    assert reqs[0].continuation_date == cont_day

    notif = db.execute(
        select(Notification).where(
            Notification.user_id == head_u.id, Notification.type == "continuation_requested",
        )
    ).scalar_one_or_none()
    assert notif is not None


def test_approval_unlocks_continuation(flag_on, client, author, pm_header, db):
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY

    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": cont_day.isoformat(),
    }).json()
    assert req["status"] == "pending"

    client.post(f"{CR}/{req['id']}/approve", headers=pm_header, json={})
    _post_report(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                 on_date=cont_day, work_item_id=wi, expect=201)


def test_rejection_keeps_continuation_blocked(flag_on, client, author, pm_header):
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY

    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": cont_day.isoformat(),
    }).json()
    client.post(f"{CR}/{req['id']}/reject", headers=pm_header, json={"comment": "not justified"})

    res = _post_report(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                       on_date=cont_day, work_item_id=wi, expect=403)
    assert "rejected" in res.json()["error"]["message"].lower()


def test_pending_continuation_lets_further_days_through(flag_on, client, db, author, pm_header):
    """A pending request does not freeze the employee out: while it awaits a
    decision, further days' continuations also succeed, and no second
    request is created (still exactly one row for this work item)."""
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=START)
    day_1 = TODAY - timedelta(days=1)
    day_2 = TODAY

    client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": day_1.isoformat(),
    })
    _post_report(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                 on_date=day_1, work_item_id=wi, expect=201)
    _post_report(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                 on_date=day_2, work_item_id=wi, expect=201)

    assert db.query(ContinuationRequest).filter_by(work_item_id=wi).count() == 1


# --------------------------------------------------------------------------
# maximum two activities per report interacts with continuation approval
# --------------------------------------------------------------------------
def test_pending_continuation_counts_as_one_activity(flag_on, client, author, pm_header, db):
    """An overdue LS continuation that auto-creates a pending approval request
    still counts as ONE activity row: pairing it with one new activity is
    still just two (allowed), and a third is rejected regardless."""
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)  # due the same day it starts
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY

    res = client.post(BASE, headers=a["header"], json={
        "report_date": cont_day.isoformat(), "day_status": "work_at_office",
        "location": "chennai",
        "tasks": [
            {"project_id": str(a["project"].id), "description": "continue A",
             "sub_activity_id": sub["id"], "work_item_id": wi},
            {"project_id": str(a["project"].id), "description": "new B", "minutes_spent": 30},
        ],
    })
    assert res.status_code == 201, res.text
    body = res.json()
    assert len(body["tasks"]) == 2
    assert body["tasks"][0]["continuation_approval_status"] == "pending"

    res3 = client.patch(f"{BASE}/{body['id']}", headers=a["header"], json={
        "tasks": [
            {"project_id": str(a["project"].id), "description": "continue A",
             "sub_activity_id": sub["id"], "work_item_id": wi},
            {"project_id": str(a["project"].id), "description": "new B", "minutes_spent": 30},
            {"project_id": str(a["project"].id), "description": "new C", "minutes_spent": 30},
        ],
    })
    assert res3.status_code == 422, res3.text
    assert "maximum of 2 activities" in res3.json()["error"]["message"]


def test_rejected_continuation_frees_activity_slot(flag_on, client, author, pm_header, db):
    """Once a Project Head rejects a lump-sum continuation, its row is
    withdrawn from the report, freeing the daily two-activity slot it held so
    the employee can record a different second activity in its place."""
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY

    res = client.post(BASE, headers=a["header"], json={
        "report_date": cont_day.isoformat(), "day_status": "work_at_office",
        "location": "chennai",
        "tasks": [
            {"project_id": str(a["project"].id), "description": "continue A",
             "sub_activity_id": sub["id"], "work_item_id": wi},
            {"project_id": str(a["project"].id), "description": "new B", "minutes_spent": 30},
        ],
    })
    assert res.status_code == 201, res.text
    report_id = res.json()["id"]

    req = db.query(ContinuationRequest).filter_by(work_item_id=wi).one()
    reject_res = client.post(f"{CR}/{req.id}/reject", headers=pm_header, json={"comment": "not justified"})
    assert reject_res.status_code == 200, reject_res.text

    fetched = client.get(f"{BASE}/{report_id}", headers=a["header"]).json()
    assert len(fetched["tasks"]) == 1
    assert fetched["tasks"][0]["description"] == "new B"

    res2 = client.patch(f"{BASE}/{report_id}", headers=a["header"], json={
        "tasks": [
            {"project_id": str(a["project"].id), "description": "new B", "minutes_spent": 30},
            {"project_id": str(a["project"].id), "description": "new D", "minutes_spent": 30},
        ],
    })
    assert res2.status_code == 200, res2.text
    assert len(res2.json()["tasks"]) == 2


def test_lost_race_uses_savepoint_and_does_not_corrupt_report_save(
    flag_on, client, db, author, pm_header, monkeypatch,
):
    """Forces get_or_create_pending_for_continuation's IntegrityError branch
    for real: a genuine second Postgres session commits a competing pending
    ContinuationRequest for the SAME work item between this function's own
    existence-check and its own insert (a real lost race, not a pre-existing
    row the existence-check would have found and short-circuited on, per
    test_pending_continuation_lets_further_days_through above never exercising
    this branch at all).

    This report save has TWO tasks: task A (a lump-sum item still well within
    its allowed duration - never gated, its WorkItem row flushes normally
    first) and task B (the overdue lump-sum item that loses the race). Before
    the fix, get_or_create_pending_for_continuation's plain db.rollback() on
    the IntegrityError would discard the WHOLE transaction so far - including
    task A's already-flushed WorkItem and the report/period rows - even
    though the save ultimately "succeeds". This test proves task A's data and
    the report itself survive intact, and exactly one ContinuationRequest
    (the concurrent winner) exists for task B's work item afterward."""
    import uuid as uuid_mod

    from app.core.database import SessionLocal
    from app.modules.continuation_requests import service as cr_service
    from app.modules.continuation_requests.models import ContinuationRequestStatus
    from app.modules.work_reports.models import WorkItem

    a = author()
    _, sub_a = _lumpsum_sub(client, pm_header, name="LumpA", period=6)  # within duration
    _, sub_b = _lumpsum_sub(client, pm_header, name="LumpB", period=1)  # overdue

    # Both work items start on the same day - a single employee can only have
    # one report per date, so start them together in one report with two tasks.
    started = client.post(BASE, headers=a["header"], json={
        "report_date": START.isoformat(), "day_status": "work_at_office",
        "location": "chennai",
        "tasks": [
            {"project_id": str(a["project"].id), "description": "work A", "sub_activity_id": sub_a["id"]},
            {"project_id": str(a["project"].id), "description": "work B", "sub_activity_id": sub_b["id"]},
        ],
    })
    assert started.status_code == 201, started.text
    started_tasks = {t["sub_activity_id"]: t["work_item_id"] for t in started.json()["tasks"]}
    wi_a = started_tasks[sub_a["id"]]
    wi_b = started_tasks[sub_b["id"]]
    cont_day = TODAY

    real_pending = cr_service._pending_for_work_item
    raced = {"done": False}

    def fake_pending(db_arg, work_item_id):
        if not raced["done"] and str(work_item_id) == wi_b:
            raced["done"] = True
            # Simulate a concurrent request that wins the race: on a totally
            # separate session/connection, insert and COMMIT a competing
            # pending row for the same work item - invisible to this check
            # (exactly as a genuine race would be), but which WILL conflict
            # when this session's own flush attempts its insert below.
            other = SessionLocal()
            try:
                item = other.get(WorkItem, uuid_mod.UUID(wi_b))
                competing = ContinuationRequest(
                    employee_id=item.employee_id, work_item_id=item.id,
                    project_id=item.project_id, sub_activity_id=item.sub_activity_id,
                    original_report_date=item.started_on,
                    allowed_duration_days=item.target_days, due_date=item.due_date,
                    continuation_date=cont_day, status=ContinuationRequestStatus.pending.value,
                )
                other.add(competing)
                other.commit()
            finally:
                other.close()
            return None
        return real_pending(db_arg, work_item_id)

    monkeypatch.setattr(cr_service, "_pending_for_work_item", fake_pending)

    res = client.post(BASE, headers=a["header"], json={
        "report_date": cont_day.isoformat(), "day_status": "work_at_office",
        "location": "chennai",
        "tasks": [
            {"project_id": str(a["project"].id), "description": "work A",
             "sub_activity_id": sub_a["id"], "work_item_id": wi_a},
            {"project_id": str(a["project"].id), "description": "work B",
             "sub_activity_id": sub_b["id"], "work_item_id": wi_b},
        ],
    })
    assert res.status_code == 201, res.text
    body = res.json()
    task_work_items = {t["work_item_id"] for t in body["tasks"]}
    assert task_work_items == {wi_a, wi_b}

    # The report is genuinely persisted and retrievable - not corrupted by a
    # whole-transaction rollback triggered deep inside task B's processing.
    fetched = client.get(f"{BASE}/{body['id']}", headers=a["header"])
    assert fetched.status_code == 200, fetched.text
    fetched_work_items = {t["work_item_id"] for t in fetched.json()["tasks"]}
    assert fetched_work_items == {wi_a, wi_b}

    # Exactly one ContinuationRequest exists for the raced work item - the
    # concurrent winner, reused (no duplicate, no crash).
    reqs = db.query(ContinuationRequest).filter_by(work_item_id=wi_b).all()
    assert len(reqs) == 1
    assert reqs[0].status == "pending"

    # Task A's own work item is untouched by task B's race - no leftover
    # ContinuationRequest was ever created for it.
    assert db.query(ContinuationRequest).filter_by(work_item_id=wi_a).count() == 0


def test_update_report_path_auto_requests_continuation(flag_on, client, db, author, pm_header):
    """The auto-request gate must fire through the report-UPDATE path too
    (PATCH /work-reports/{id}), not just through create_work_report — this
    exercises update_work_report's legacy "tasks" branch, which threads its
    own new_continuation_requests accumulator separately from create's."""
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)  # due the same day it starts
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY

    # A draft report for cont_day with no activity yet (a leave-type day).
    created = client.post(BASE, headers=a["header"], json={
        "report_date": cont_day.isoformat(), "day_status": "leave", "location": "chennai",
    })
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]

    # Still a draft: update it in place to add the continuation task, past the
    # item's allowed duration.
    res = client.patch(f"{BASE}/{report_id}", headers=a["header"], json={
        "day_status": "work_at_office",
        "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "sub_activity_id": sub["id"], "work_item_id": wi,
        }],
    })
    assert res.status_code == 200, res.text
    assert res.json()["tasks"][0]["work_item_id"] == wi

    reqs = db.query(ContinuationRequest).filter_by(work_item_id=wi).all()
    assert len(reqs) == 1
    assert reqs[0].status == "pending"


# --------------------------------------------------------------------------
# duplicate prevention
# --------------------------------------------------------------------------

def test_duplicate_pending_request_returns_existing(flag_on, client, author, pm_header, db):
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY

    body = {"work_item_id": wi, "continuation_date": cont_day.isoformat()}
    r1 = client.post(CR, headers=a["header"], json=body).json()
    r2 = client.post(CR, headers=a["header"], json=body).json()
    assert r1["id"] == r2["id"]
    assert db.query(ContinuationRequest).filter_by(work_item_id=wi).count() == 1


# --------------------------------------------------------------------------
# routing / authorization
# --------------------------------------------------------------------------

def test_correct_head_receives_request(flag_on, client, make_user, make_employee, make_project,
                                        make_project_member, login, pm_header):
    head_u = make_user("head1@x.com", role=UserRole.employee)
    head = make_employee(employee_code="H1", user_id=head_u.id)
    emp_u = make_user("emp1@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E2", user_id=emp_u.id)
    project = make_project(code="P-H1", status=ProjectStatus.active, head_employee_id=head.id)
    make_project_member(project_id=project.id, employee_id=emp.id)
    emp_header = login("emp1@x.com")
    head_header = login("head1@x.com")

    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, emp_header, project_id=project.id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY
    req = client.post(CR, headers=emp_header, json={
        "work_item_id": wi, "continuation_date": cont_day.isoformat(),
    }).json()

    pending = client.get(f"{CR}/pending", headers=head_header).json()
    assert any(r["id"] == req["id"] for r in pending)

    other_u = make_user("other1@x.com", role=UserRole.employee)
    make_employee(employee_code="O1", user_id=other_u.id)
    other_header = login("other1@x.com")
    pending_other = client.get(f"{CR}/pending", headers=other_header).json()
    assert not any(r["id"] == req["id"] for r in pending_other)


def test_no_head_falls_back_to_manager_and_pm_can_still_approve(
    flag_on, client, db, make_user, make_employee, make_project, make_project_member, login, pm_header,
):
    from sqlalchemy import select

    from app.modules.notifications.models import Notification

    mgr_u = make_user("mgr1@x.com", role=UserRole.employee)
    mgr = make_employee(employee_code="M1", user_id=mgr_u.id)
    emp_u = make_user("emp2@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E3", user_id=emp_u.id, manager_id=mgr.id)
    project = make_project(code="P-NM", status=ProjectStatus.active, head_employee_id=None)
    make_project_member(project_id=project.id, employee_id=emp.id)
    emp_header = login("emp2@x.com")

    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, emp_header, project_id=project.id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY
    client.post(CR, headers=emp_header, json={
        "work_item_id": wi, "continuation_date": cont_day.isoformat(),
    })

    notif = db.execute(
        select(Notification).where(
            Notification.user_id == mgr_u.id, Notification.type == "continuation_requested",
        )
    ).scalar_one_or_none()
    assert notif is not None

    req = db.execute(
        select(ContinuationRequest).where(ContinuationRequest.employee_id == emp.id)
    ).scalar_one()
    res = client.post(f"{CR}/{req.id}/approve", headers=pm_header, json={})
    assert res.status_code == 200, res.text


def test_reassigned_head_takes_over_review_authority(
    flag_on, client, db, make_user, make_employee, make_project, make_project_member, login, pm_header,
):
    head_a_u = make_user("heada@x.com", role=UserRole.employee)
    head_a = make_employee(employee_code="HA", user_id=head_a_u.id)
    head_b_u = make_user("headb@x.com", role=UserRole.employee)
    head_b = make_employee(employee_code="HB", user_id=head_b_u.id)
    project = make_project(code="P-RH", status=ProjectStatus.active, head_employee_id=head_a.id)

    emp_u = make_user("empr@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="ER", user_id=emp_u.id)
    make_project_member(project_id=project.id, employee_id=emp.id)
    emp_header = login("empr@x.com")

    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, emp_header, project_id=project.id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY
    req = client.post(CR, headers=emp_header, json={
        "work_item_id": wi, "continuation_date": cont_day.isoformat(),
    }).json()

    project.head_employee_id = head_b.id
    db.add(project)
    db.commit()

    h_a = login("heada@x.com")
    res_a = client.post(f"{CR}/{req['id']}/approve", headers=h_a, json={})
    assert res_a.status_code == 403, res_a.text

    h_b = login("headb@x.com")
    res_b = client.post(f"{CR}/{req['id']}/approve", headers=h_b, json={})
    assert res_b.status_code == 200, res_b.text


def test_unauthorized_employee_cannot_approve(flag_on, client, author, pm_header, make_user, login):
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY
    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": cont_day.isoformat(),
    }).json()

    make_user("stranger@x.com", role=UserRole.employee)
    stranger = login("stranger@x.com")
    res = client.post(f"{CR}/{req['id']}/approve", headers=stranger, json={})
    assert res.status_code == 403, res.text


def test_self_approval_blocked(flag_on, client, author, pm_header, db):
    """The Project Head IS the requesting employee (self-routed) - the review
    endpoint must still 403, mirroring leave's self-review guard."""
    a = author()
    a["project"].head_employee_id = a["emp"].id
    db.add(a["project"])
    db.commit()
    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY
    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": cont_day.isoformat(),
    }).json()
    res = client.post(f"{CR}/{req['id']}/approve", headers=a["header"], json={})
    assert res.status_code == 403, res.text


# --------------------------------------------------------------------------
# decisions: approve / reject + notifications
# --------------------------------------------------------------------------

def test_head_can_approve_and_notifies_employee(
    flag_on, client, db, author, pm_header, make_user, make_employee, login,
):
    from sqlalchemy import select

    from app.modules.notifications.models import Notification

    a = author()
    head_u = make_user("head3@x.com", role=UserRole.employee)
    head = make_employee(employee_code="H3", user_id=head_u.id)
    a["project"].head_employee_id = head.id
    db.add(a["project"])
    db.commit()
    head_header = login("head3@x.com")

    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY
    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": cont_day.isoformat(),
    }).json()

    res = client.post(f"{CR}/{req['id']}/approve", headers=head_header, json={"comment": "go ahead"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"
    assert res.json()["reviewer_id"] == str(head.id)

    notif = db.execute(
        select(Notification).where(
            Notification.user_id == a["user"].id, Notification.type == "continuation_approved",
        )
    ).scalar_one_or_none()
    assert notif is not None


def test_head_can_reject_and_notifies_employee(
    flag_on, client, db, author, pm_header, make_user, make_employee, login,
):
    from sqlalchemy import select

    from app.modules.notifications.models import Notification

    a = author()
    head_u = make_user("head4@x.com", role=UserRole.employee)
    head = make_employee(employee_code="H4", user_id=head_u.id)
    a["project"].head_employee_id = head.id
    db.add(a["project"])
    db.commit()
    head_header = login("head4@x.com")

    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY
    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": cont_day.isoformat(),
    }).json()

    res = client.post(f"{CR}/{req['id']}/reject", headers=head_header, json={"comment": "not justified"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "rejected"

    notif = db.execute(
        select(Notification).where(
            Notification.user_id == a["user"].id, Notification.type == "continuation_rejected",
        )
    ).scalar_one_or_none()
    assert notif is not None

    pending = client.get(f"{CR}/pending", headers=head_header).json()
    assert not any(r["id"] == req["id"] for r in pending)


def test_pending_and_all_requests_reflect_decisions(flag_on, client, author, pm_header):
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY
    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": cont_day.isoformat(),
    }).json()

    pending_before = client.get(f"{CR}/pending", headers=pm_header).json()
    assert any(r["id"] == req["id"] for r in pending_before)

    client.post(f"{CR}/{req['id']}/approve", headers=pm_header, json={})

    pending_after = client.get(f"{CR}/pending", headers=pm_header).json()
    assert not any(r["id"] == req["id"] for r in pending_after)

    history = client.get(CR, headers=pm_header, params={"status": "approved"}).json()
    assert any(r["id"] == req["id"] for r in history["items"])
    assert history["total"] >= 1


def test_task_with_quantity_continuation_never_gated(flag_on, client, author, pm_header):
    """TASK_WITH_QUANTITY must continue exactly as before Phase 2 - never
    gated by the lump-sum continuation-approval check, even when overdue."""
    a = author()
    _, sub = _quantity_task_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY
    _post_report(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                 on_date=cont_day, work_item_id=wi, expect=201)


# --------------------------------------------------------------------------
# read endpoints
# --------------------------------------------------------------------------

def test_employee_can_read_own_request_head_and_pm_can_too(flag_on, client, db, author, pm_header,
                                                            make_user, make_employee, login):
    a = author()
    head_u = make_user("head5@x.com", role=UserRole.employee)
    head = make_employee(employee_code="H5", user_id=head_u.id)
    a["project"].head_employee_id = head.id
    db.add(a["project"])
    db.commit()
    head_header = login("head5@x.com")

    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY
    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": cont_day.isoformat(),
    }).json()

    assert client.get(f"{CR}/{req['id']}", headers=a["header"]).status_code == 200
    assert client.get(f"{CR}/{req['id']}", headers=head_header).status_code == 200
    assert client.get(f"{CR}/{req['id']}", headers=pm_header).status_code == 200


def test_stranger_cannot_read_request(flag_on, client, author, pm_header, make_user, login):
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=START)
    cont_day = TODAY
    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": cont_day.isoformat(),
    }).json()

    make_user("stranger2@x.com", role=UserRole.employee)
    stranger = login("stranger2@x.com")
    res = client.get(f"{CR}/{req['id']}", headers=stranger)
    assert res.status_code == 403, res.text


# --------------------------------------------------------------------------
# notification destination (UX): the employee is taken to the affected REPORT
# --------------------------------------------------------------------------
# The decision notification answers "what happened to my work?", so it deep-links
# to the report the work was entered on, not to the reviewer's request record.
# /lump-sum-activity/{id} stays the REVIEWER's page and is only the fallback for
# a request with no entry behind it.

def _notif_url(db, user_id, type_):
    from sqlalchemy import select

    from app.modules.notifications.models import Notification

    n = db.execute(
        select(Notification).where(
            Notification.user_id == user_id, Notification.type == type_,
        )
    ).scalar_one_or_none()
    assert n is not None, f"no {type_} notification"
    return n.target_url


def _continued_report(client, db, author_fixture, pm_header, make_user, make_employee, login,
                      *, suffix):
    """An employee with a Head, a 1-day lump-sum already started, and a SUBMITTED
    continuation report for TODAY - which auto-raises the pending request. Returns
    (author, head_header, report_id, request_id).

    Submitted, because that is when a Head normally decides: a report still in
    draft when the decision lands is the edge case below."""
    a = author_fixture(email=f"emp{suffix}@x.com", code=f"E{suffix}", proj_code=f"P-{suffix}")
    head_u = make_user(f"head{suffix}@x.com", role=UserRole.employee)
    head = make_employee(employee_code=f"H{suffix}", user_id=head_u.id)
    a["project"].head_employee_id = head.id
    db.add(a["project"])
    db.commit()

    _, sub = _lumpsum_sub(client, pm_header, name=f"Lumpsum{suffix}", period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id,
                          sub_id=sub["id"], on_date=START)
    saved = _post_report(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                         on_date=TODAY, work_item_id=wi).json()
    row = saved["tasks"][0]
    assert row["continuation_approval_status"] == "pending"
    assert client.post(f"{BASE}/{saved['id']}/submit", headers=a["header"]).status_code == 200
    return a, login(f"head{suffix}@x.com"), saved["id"], row["continuation_request_id"]


def test_approved_notification_links_to_the_affected_report(
    flag_on, client, db, author, pm_header, make_user, make_employee, login,
):
    a, head_header, report_id, req_id = _continued_report(
        client, db, author, pm_header, make_user, make_employee, login, suffix="20",
    )
    res = client.post(f"{CR}/{req_id}/approve", headers=head_header, json={"comment": "ok"})
    assert res.status_code == 200, res.text

    assert _notif_url(db, a["user"].id, "continuation_approved") == f"/work-reports/{report_id}"


def test_rejected_notification_links_to_the_affected_report(
    flag_on, client, db, author, pm_header, make_user, make_employee, login,
):
    """Resolved BEFORE the rejection withdraws the stamped rows - otherwise there
    would be nothing left to resolve the report from."""
    a, head_header, report_id, req_id = _continued_report(
        client, db, author, pm_header, make_user, make_employee, login, suffix="21",
    )
    res = client.post(f"{CR}/{req_id}/reject", headers=head_header, json={"comment": "no"})
    assert res.status_code == 200, res.text

    assert _notif_url(db, a["user"].id, "continuation_rejected") == f"/work-reports/{report_id}"
    # The rejection itself is unchanged: the row is withdrawn from the report,
    # which is reopened carrying the note the report page shows the author.
    detail = client.get(f"{BASE}/{report_id}", headers=a["header"]).json()
    assert detail["tasks"] == []
    assert detail["status"] == "granted"
    assert "rejected" in (detail["review_note"] or "")


def test_rejected_draft_report_still_links_to_the_report(
    flag_on, client, db, author, pm_header, make_user, make_employee, login,
):
    """A report still in DRAFT when the rejection lands: the row is withdrawn and
    the destination is still the report, but nothing reopens it (it was never
    submitted) so it carries no withdrawal note - the notification's own message
    is what explains the removal."""
    a = author(email="emp25@x.com", code="E25", proj_code="P-25")
    head_u = make_user("head25@x.com", role=UserRole.employee)
    head = make_employee(employee_code="H25", user_id=head_u.id)
    a["project"].head_employee_id = head.id
    db.add(a["project"])
    db.commit()

    _, sub = _lumpsum_sub(client, pm_header, name="Lumpsum25", period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id,
                          sub_id=sub["id"], on_date=START)
    saved = _post_report(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                         on_date=TODAY, work_item_id=wi).json()
    req_id = saved["tasks"][0]["continuation_request_id"]
    client.post(f"{CR}/{req_id}/reject", headers=login("head25@x.com"), json={})

    assert _notif_url(db, a["user"].id, "continuation_rejected") == f"/work-reports/{saved['id']}"
    detail = client.get(f"{BASE}/{saved['id']}", headers=a["header"]).json()
    assert detail["tasks"] == []
    assert detail["status"] == "draft"
    assert detail["review_note"] is None


def test_decision_notification_falls_back_to_the_request_page_with_no_entry(
    flag_on, client, db, author, pm_header, make_user, make_employee, login,
):
    """A request raised through the explicit endpoint and decided before the
    employee ever reported that day has no report to link to."""
    a = author(email="emp22@x.com", code="E22", proj_code="P-22")
    head_u = make_user("head22@x.com", role=UserRole.employee)
    head = make_employee(employee_code="H22", user_id=head_u.id)
    a["project"].head_employee_id = head.id
    db.add(a["project"])
    db.commit()

    _, sub = _lumpsum_sub(client, pm_header, name="Lumpsum22", period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id,
                          sub_id=sub["id"], on_date=START)
    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": TODAY.isoformat(),
    }).json()
    client.post(f"{CR}/{req['id']}/approve", headers=login("head22@x.com"), json={})

    assert _notif_url(db, a["user"].id, "continuation_approved") == f"/lump-sum-activity/{req['id']}"


def test_reviewer_notification_destination_is_unchanged(
    flag_on, client, db, author, pm_header, make_user, make_employee, login,
):
    """The OTHER notification this feature sends is untouched: the reviewer still
    lands on their own queue, filtered to the pending request."""
    _a, _head_header, _report_id, req_id = _continued_report(
        client, db, author, pm_header, make_user, make_employee, login, suffix="23",
    )
    from sqlalchemy import select

    from app.modules.notifications.models import Notification

    n = db.execute(
        select(Notification).where(Notification.type == "continuation_requested")
    ).scalars().all()
    assert any(x.target_url == f"/lump-sum-activity?queue=pending&id={req_id}" for x in n)


def test_reviewer_can_still_open_the_request_detail(
    flag_on, client, db, author, pm_header, make_user, make_employee, login,
):
    """The page the Back button lives on: GET /continuation-requests/{id} still
    serves the full record to the Head and to the PM."""
    _a, head_header, _report_id, req_id = _continued_report(
        client, db, author, pm_header, make_user, make_employee, login, suffix="24",
    )
    res = client.get(f"{CR}/{req_id}", headers=head_header)
    assert res.status_code == 200, res.text
    assert res.json()["id"] == req_id
    assert client.get(f"{CR}/{req_id}", headers=pm_header).status_code == 200
