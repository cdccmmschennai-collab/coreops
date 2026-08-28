"""The approval LIFECYCLE of a lump-sum continuation: PENDING -> APPROVED /
REJECTED.

Phase 3 correction. The weekly foundation (Fri-Thu confinement, work-day
duration, frozen started_on/due_date, skipped days, TASK_WITH_QUANTITY) is
settled and is only asserted here as non-regression. What these tests pin down
is what a submitted continuation MEANS before and after the Project Head
decides:

    within the allowance   -> ordinary work, no request, no approval state
    past the allowance     -> PENDING: entered, submitted, but NOT accepted work
    approved               -> ordinary work, on the SAME work item, no new
                              allowance
    rejected               -> withdrawn from the report entirely; other
                              activities on that report survive untouched

The shape is deliberately the same as an activity request: the employee enters
it, it waits for a decision, and only an approval makes it part of the accepted
report.

Every date sits inside ONE past Friday-Thursday cycle, so each scenario is one
an employee can actually reach through the form (open tasks are only suggested
inside their own cycle) and no report is ever dated in the future.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.modules.activity_master.service import compute_week_bounds
from app.modules.continuation_requests.models import ContinuationRequest
from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole
from app.modules.work_reports.models import WorkItem

BASE = "/api/v1/work-reports"
OPEN_TASKS = f"{BASE}/open-tasks"
CR = "/api/v1/continuation-requests"
TODAY = date.today()
# The PREVIOUS Friday-Thursday cycle: seven consecutive past days, all inside
# the editable report window (current + previous month).
PREV_FRI = compute_week_bounds(TODAY)[0] - timedelta(days=7)


def _d(offset: int) -> date:
    """_d(0) is the previous cycle's Friday, _d(6) its Thursday."""
    return PREV_FRI + timedelta(days=offset)


@pytest.fixture()
def flag_on():
    prev = settings.TASK_CONTINUATION_ENABLED
    settings.TASK_CONTINUATION_ENABLED = True
    try:
        yield
    finally:
        settings.TASK_CONTINUATION_ENABLED = prev


@pytest.fixture()
def head(make_user, make_employee, login):
    """A Project Head - the reviewer the feature is actually about."""
    def _make(*, email="head@x.com", code="H-1"):
        u = make_user(email, role=UserRole.employee)
        e = make_employee(employee_code=code, user_id=u.id)
        return {"user": u, "emp": e, "header": login(email)}

    return _make


@pytest.fixture()
def author(make_user, make_employee, make_project, make_project_member, login):
    def _make(*, email="emp@x.com", code="E-1", proj_code="P-1", head_id=None):
        u = make_user(email, role=UserRole.employee)
        e = make_employee(employee_code=code, user_id=u.id)
        p = make_project(code=proj_code, status=ProjectStatus.active,
                         head_employee_id=head_id)
        make_project_member(project_id=p.id, employee_id=e.id)
        return {"user": u, "emp": e, "project": p, "header": login(email)}

    return _make


@pytest.fixture()
def pm_header(auth_header):
    return auth_header(email="pm@x.com", role=UserRole.project_manager)


@pytest.fixture()
def team(flag_on, client, author, head, pm_header):
    """The standard cast: an employee on a project whose Head can review."""
    h = head()
    a = author(head_id=h["emp"].id)
    return {"head": h, "author": a, "pm": pm_header}


# ---------- builders --------------------------------------------------------
def _lumpsum_sub(client, admin, *, name="Lumpsum", period=2):
    """Lump-sum = a task benchmark with NO relevant_count_field."""
    a = client.post("/api/v1/activity-master/activities",
                    json={"name": f"Activity {name}"}, headers=admin).json()
    sub = client.post(
        f"/api/v1/activity-master/activities/{a['id']}/sub-activities",
        json={"name": name, "benchmark_type": "TASK_STATUS_ONLY"}, headers=admin,
    ).json()
    client.patch(f"/api/v1/activity-master/sub-activities/{sub['id']}",
                 json={"benchmark_period_days": period}, headers=admin)
    return a, sub


def _quantity_sub(client, admin, *, name="Quantity", period=1):
    """TASK_WITH_QUANTITY: task-bearing (it gets a work item) but NOT lump-sum."""
    a = client.post("/api/v1/activity-master/activities",
                    json={"name": f"Activity {name}"}, headers=admin).json()
    return a, client.post(
        f"/api/v1/activity-master/activities/{a['id']}/sub-activities",
        json={"name": name, "benchmark_type": "TASK_WITH_QUANTITY",
              "relevant_count_field": "pages", "benchmark_value": 100,
              "benchmark_period_days": period},
        headers=admin,
    ).json()


def _daily_sub(client, admin, *, name="Daily"):
    """A plain daily-quantity activity: no work item, never continued. Used as
    the "other valid activity" a rejection must leave alone."""
    a = client.post("/api/v1/activity-master/activities",
                    json={"name": f"Activity {name}"}, headers=admin).json()
    return a, client.post(
        f"/api/v1/activity-master/activities/{a['id']}/sub-activities",
        json={"name": name, "benchmark_type": "NUMERIC_DAILY",
              "relevant_count_field": "pages", "benchmark_value": 100},
        headers=admin,
    ).json()


def _task(project_id, sub_id, *, work_item_id=None, is_completed=False, **extra):
    # count_field/count_value: an LS row now requires a count (see
    # test_lumpsum_count_field.py). Defaulted here so every builder in this
    # file — which is about the continuation/approval lifecycle, not the
    # count feature — keeps passing it without each call site restating it;
    # a non-lumpsum sub (TASK_WITH_QUANTITY, NUMERIC_DAILY) simply has it
    # cleared server-side, same as before.
    t = {"project_id": str(project_id), "description": "work",
         "sub_activity_id": sub_id, "is_completed": is_completed,
         "count_field": "tags", "count_value": 25, **extra}
    if work_item_id is not None:
        t["work_item_id"] = str(work_item_id)
    return t


def _post(client, header, *, on_date, tasks, expect=201):
    res = client.post(BASE, headers=header, json={
        "report_date": on_date.isoformat(), "day_status": "work_at_office",
        "location": "chennai", "tasks": tasks,
    })
    assert res.status_code == expect, res.text
    return res


def _one(client, header, *, project_id, sub_id, on_date, work_item_id=None,
         is_completed=False, expect=201, **extra):
    return _post(client, header, on_date=on_date, expect=expect, tasks=[
        _task(project_id, sub_id, work_item_id=work_item_id,
              is_completed=is_completed, **extra)
    ])


def _start(client, header, *, project_id, sub_id, on_date):
    return _one(client, header, project_id=project_id, sub_id=sub_id,
                on_date=on_date).json()["tasks"][0]["work_item_id"]


def _row(res, index=0):
    return res.json()["tasks"][index]


def _submit(client, header, report_id):
    res = client.post(f"{BASE}/{report_id}/submit", headers=header, json={})
    assert res.status_code == 200, res.text
    return res.json()


def _get(client, header, report_id):
    res = client.get(f"{BASE}/{report_id}", headers=header)
    assert res.status_code == 200, res.text
    return res.json()


def _requests(db, employee_id):
    return list(db.execute(
        select(ContinuationRequest).where(
            ContinuationRequest.employee_id == employee_id
        ).order_by(ContinuationRequest.requested_at)
    ).scalars().all())


def _open_task(client, header, *, report_date, work_item_id):
    ot = client.get(OPEN_TASKS, headers=header,
                    params={"report_date": report_date.isoformat()}).json()
    return next((t for t in ot["items"] if t["work_item_id"] == work_item_id), None)


# ==========================================================================
# 1. within the allowance -> no approval anywhere in sight
# ==========================================================================
def test_continuation_within_allowance_needs_no_approval(client, team, db):
    a, pm = team["author"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=3)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))

    res = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
               on_date=_d(1), work_item_id=wid)          # day 2 of 3
    row = _row(res)
    assert row["continuation_request_id"] is None
    assert row["continuation_approval_status"] is None
    assert _requests(db, a["emp"].id) == []


# ==========================================================================
# 2. past the allowance -> PENDING
# ==========================================================================
def test_continuation_past_allowance_is_pending(client, team, db):
    a, pm = team["author"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=1)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))

    res = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
               on_date=_d(2), work_item_id=wid)
    row = _row(res)
    assert row["continuation_approval_status"] == "pending"

    reqs = _requests(db, a["emp"].id)
    assert len(reqs) == 1
    assert reqs[0].status == "pending"
    assert str(reqs[0].id) == row["continuation_request_id"]
    # The request is about THIS work item and THIS day - it is not a new
    # activity of its own.
    assert str(reqs[0].work_item_id) == wid
    assert reqs[0].continuation_date == _d(2)


def test_pending_state_survives_submission(client, team):
    """Submitting the report files the work; it does not decide the request.
    'Submitted' and 'approved continuation' are different things."""
    a, pm = team["author"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=1)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    res = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
               on_date=_d(2), work_item_id=wid)

    submitted = _submit(client, a["header"], res.json()["id"])
    assert submitted["status"] == "submitted"
    assert submitted["tasks"][0]["continuation_approval_status"] == "pending"


def test_editing_the_report_keeps_the_row_tied_to_its_decision(client, team, db):
    """A report edit deletes and rewrites its task rows. The rewritten
    continuation must come back tied to the SAME pending request - otherwise an
    edit would quietly launder pending work into ordinary work and put it out of
    the rejection's reach."""
    a, pm = team["author"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=1)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    res = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
               on_date=_d(2), work_item_id=wid)
    report_id = res.json()["id"]
    req = _requests(db, a["emp"].id)[0]

    edited = client.patch(f"{BASE}/{report_id}", headers=a["header"], json={
        "day_status": "work_at_office", "location": "chennai",
        "tasks": [_task(a["project"].id, sub["id"], work_item_id=wid,
                        minutes_spent=90)],
    })
    assert edited.status_code == 200, edited.text
    assert _row(edited)["continuation_approval_status"] == "pending"
    assert _row(edited)["continuation_request_id"] == str(req.id)
    # The edit raised no second request - one continuation, one decision.
    assert len(_requests(db, a["emp"].id)) == 1


# ==========================================================================
# 3. a PENDING continuation is not treated as approved valid work
# ==========================================================================
def test_pending_continuation_can_still_complete_the_activity(client, team, db):
    """PATCH /tasks/{id}/completion, the explicit "mark this complete" action.

    A pending decision is about whether the continuation work is ACCEPTED, not
    about whether the employee may say the task is finished. Refusing here (the
    old behaviour) told an employee who had genuinely finished the activity that
    they could not record that fact until someone else acted."""
    import uuid as _uuid

    a, pm = team["author"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=1)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    res = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
               on_date=_d(2), work_item_id=wid)
    row_id = _row(res)["id"]

    done = client.patch(f"{BASE}/tasks/{row_id}/completion", headers=a["header"],
                        json={"is_completed": True})
    assert done.status_code == 200, done.text
    assert db.get(WorkItem, _uuid.UUID(wid)).completed_on == _d(2)
    # Completing is not deciding: the request is still the Project Head's to make.
    reqs = _requests(db, a["emp"].id)
    assert len(reqs) == 1 and reqs[0].status == "pending"


def test_pending_continuation_accepts_the_completion_tick_and_saves_the_report(
    client, team, db
):
    """The scenario this correction exists for, through the report form.

    Aug 24: an LS activity with a one-work-day allowance is started and left
    unfinished. Aug 25: the employee continues it, which auto-raises the
    continuation request - and finishes it. Ticking "Mark task fully completed"
    on that continuation report must save, and must actually complete the
    activity. Previously the tick was silently swallowed, so the employee's
    report claimed nothing about a task they had in fact finished."""
    import uuid as _uuid

    a, pm = team["author"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=1)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))

    res = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
               on_date=_d(2), work_item_id=wid, is_completed=True)
    row = _row(res)
    # The row is stamped with the pending request AND is completed - both facts
    # are true at once, which is the whole point.
    assert row["continuation_approval_status"] == "pending"
    assert row["row_is_completed"] is True
    assert row["overall_completed_on"] == _d(2).isoformat()
    assert db.get(WorkItem, _uuid.UUID(wid)).completed_on == _d(2)

    # The report submits, and submitting still does not decide the request.
    submitted = _submit(client, a["header"], res.json()["id"])
    assert submitted["status"] == "submitted"
    assert submitted["tasks"][0]["continuation_approval_status"] == "pending"
    assert submitted["tasks"][0]["row_is_completed"] is True

    reqs = _requests(db, a["emp"].id)
    assert len(reqs) == 1 and reqs[0].status == "pending"


def test_approval_keeps_the_completed_continuation_row_valid(client, team, db):
    """Approving after the employee already completed on the pending day changes
    nothing about the completion - it only turns the row into accepted work."""
    import uuid as _uuid

    a, h, pm = team["author"], team["head"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=1)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    res = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
               on_date=_d(2), work_item_id=wid, is_completed=True)
    report_id = res.json()["id"]
    req = _requests(db, a["emp"].id)[0]

    ok = client.post(f"{CR}/{req.id}/approve", headers=h["header"], json={})
    assert ok.status_code == 200, ok.text

    after = _get(client, a["header"], report_id)
    assert len(after["tasks"]) == 1
    assert after["tasks"][0]["continuation_approval_status"] == "approved"
    assert after["tasks"][0]["row_is_completed"] is True
    # Same work item, same completion date - approval grants nothing new.
    item = db.get(WorkItem, _uuid.UUID(wid))
    db.refresh(item)
    assert item.completed_on == _d(2)
    assert item.started_on == _d(0)


def test_rejection_undoes_a_completion_made_on_the_rejected_day(client, team, db):
    """The other side of allowing completion while pending: a refused day must
    not leave the activity looking finished. The existing withdrawal already
    clears a completion stamped on a withdrawn day - this pins that it does."""
    import uuid as _uuid

    a, h, pm = team["author"], team["head"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=1)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    res = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
               on_date=_d(2), work_item_id=wid, is_completed=True)
    report_id = res.json()["id"]
    req = _requests(db, a["emp"].id)[0]

    no = client.post(f"{CR}/{req.id}/reject", headers=h["header"],
                     json={"comment": "not approved"})
    assert no.status_code == 200, no.text

    after = _get(client, a["header"], report_id)
    assert after["tasks"] == []
    item = db.get(WorkItem, _uuid.UUID(wid))
    db.refresh(item)
    assert item.completed_on is None
    assert item.started_on == _d(0)


# ==========================================================================
# 4. APPROVED -> valid recorded work, same item, no new allowance
# ==========================================================================
def test_approval_makes_the_continuation_valid_work(client, team, db):
    a, h, pm = team["author"], team["head"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=1)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    res = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
               on_date=_d(2), work_item_id=wid)
    report_id, row_id = res.json()["id"], _row(res)["id"]
    req = _requests(db, a["emp"].id)[0]

    # The project's Head reviews it - not the PM, not the employee.
    ok = client.post(f"{CR}/{req.id}/approve", headers=h["header"], json={})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "approved"

    got = _get(client, a["header"], report_id)
    assert got["tasks"][0]["continuation_approval_status"] == "approved"
    assert got["tasks"][0]["continuation_request_id"] == str(req.id)
    # And it now behaves as ordinary work: the activity can be completed on it.
    done = client.patch(f"{BASE}/tasks/{row_id}/completion", headers=a["header"],
                        json={"is_completed": True})
    assert done.status_code == 200, done.text


def test_approved_continuation_stays_on_the_same_work_item(client, team, db):
    """Requirement: work item #123 before approval is work item #123 after it -
    same identity, same frozen history."""
    import uuid as _uuid

    a, h, pm = team["author"], team["head"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=2)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
         on_date=_d(1), work_item_id=wid)                       # day 2 of 2
    before = db.get(WorkItem, _uuid.UUID(wid))
    frozen = (before.started_on, before.due_date, before.target_days)

    res = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
               on_date=_d(2), work_item_id=wid)                 # pending
    assert _row(res)["work_item_id"] == wid

    req = _requests(db, a["emp"].id)[0]
    assert str(req.work_item_id) == wid
    client.post(f"{CR}/{req.id}/approve", headers=h["header"], json={})

    db.expire_all()
    after = db.get(WorkItem, _uuid.UUID(wid))
    assert (after.started_on, after.due_date, after.target_days) == frozen
    assert _row(res)["work_item_id"] == wid


def test_approval_grants_no_fresh_allowance(client, team, db):
    """Approval is permission to continue THIS activity, not a reset. The item
    stays over its allowance, no second work item appears, and the days after
    the approval ride on the same single request."""
    a, h, pm = team["author"], team["head"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=1)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
         on_date=_d(2), work_item_id=wid)
    req = _requests(db, a["emp"].id)[0]
    client.post(f"{CR}/{req.id}/approve", headers=h["header"], json={})

    res = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
               on_date=_d(3), work_item_id=wid)
    # Same approval, no new request raised for the extra day.
    assert _row(res)["continuation_approval_status"] == "approved"
    assert _row(res)["continuation_request_id"] == str(req.id)
    assert len(_requests(db, a["emp"].id)) == 1

    items = db.execute(
        select(WorkItem).where(WorkItem.employee_id == a["emp"].id)
    ).scalars().all()
    assert len(items) == 1

    t = _open_task(client, a["header"], report_date=_d(4), work_item_id=wid)
    assert t["days_used"] == 3            # still spending past a 1-day allowance
    assert t["lifecycle"] == "OVERDUE"
    assert t["continuation_status"] == "approved"
    assert t["requires_continuation_approval"] is False


# ==========================================================================
# 5/6. REJECTED -> the work is withdrawn, the report stops claiming it
# ==========================================================================
def test_rejection_removes_the_continuation_from_the_report(client, team, db):
    a, h, pm = team["author"], team["head"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=1)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    res = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
               on_date=_d(2), work_item_id=wid)
    report_id = res.json()["id"]
    assert _submit(client, a["header"], report_id)["status"] == "submitted"
    req = _requests(db, a["emp"].id)[0]

    out = client.post(f"{CR}/{req.id}/reject", headers=h["header"],
                      json={"comment": "not justified"})
    assert out.status_code == 200, out.text
    assert out.json()["status"] == "rejected"

    got = _get(client, a["header"], report_id)
    # The rejected continuation is gone - not present-but-flagged.
    assert got["tasks"] == []
    assert got["total_minutes"] == 0
    # ... and the report no longer stands as an accepted submitted report: it is
    # back with the employee in an editable state.
    assert got["status"] == "granted"
    # The originating day is untouched: only the rejected day was withdrawn.
    assert db.get(WorkItem, req.work_item_id) is not None


def test_rejected_continuation_cannot_be_re_entered(client, team, db):
    a, h, pm = team["author"], team["head"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=1)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
         on_date=_d(2), work_item_id=wid)
    req = _requests(db, a["emp"].id)[0]
    client.post(f"{CR}/{req.id}/reject", headers=h["header"], json={})

    res = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
               on_date=_d(3), work_item_id=wid, expect=403)
    assert "rejected" in res.json()["error"]["message"].lower()


def test_rejection_withdraws_every_day_held_under_the_same_request(client, team, db):
    """While a request is pending the employee may keep reporting; all of those
    days ride on the one decision, so all of them are withdrawn together."""
    a, h, pm = team["author"], team["head"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=1)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    first = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                 on_date=_d(2), work_item_id=wid)
    second = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                  on_date=_d(3), work_item_id=wid)
    reqs = _requests(db, a["emp"].id)
    assert len(reqs) == 1                       # one decision, not one per day
    assert _row(second)["continuation_request_id"] == str(reqs[0].id)
    _submit(client, a["header"], first.json()["id"])
    _submit(client, a["header"], second.json()["id"])

    client.post(f"{CR}/{reqs[0].id}/reject", headers=h["header"], json={})

    for res in (first, second):
        got = _get(client, a["header"], res.json()["id"])
        assert got["tasks"] == []
        assert got["status"] == "granted"


# ==========================================================================
# 7. other valid activities on the same report survive
# ==========================================================================
def test_rejection_preserves_the_other_activities_on_the_report(client, team, db):
    a, h, pm = team["author"], team["head"], team["pm"]
    _, ls = _lumpsum_sub(client, pm, period=1)
    _, daily = _daily_sub(client, pm)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=ls["id"], on_date=_d(0))

    res = _post(client, a["header"], on_date=_d(2), tasks=[
        _task(a["project"].id, ls["id"], work_item_id=wid, minutes_spent=120),
        _task(a["project"].id, daily["id"], pages_count=40, minutes_spent=180),
    ])
    report_id = res.json()["id"]
    assert _submit(client, a["header"], report_id)["total_minutes"] == 300
    req = _requests(db, a["emp"].id)[0]

    client.post(f"{CR}/{req.id}/reject", headers=h["header"], json={})

    got = _get(client, a["header"], report_id)
    assert len(got["tasks"]) == 1
    assert got["tasks"][0]["sub_activity_id"] == daily["id"]
    assert got["tasks"][0]["pages_count"] == 40
    # The report still stands on its remaining work, so it stays submitted;
    # only the withdrawn minutes are gone.
    assert got["status"] == "submitted"
    assert got["total_minutes"] == 180


def test_rejection_does_not_touch_the_earlier_within_allowance_days(client, team, db):
    """Only the days the decision was ABOUT are withdrawn. The work days the
    activity legitimately spent inside its allowance are ordinary history."""
    a, h, pm = team["author"], team["head"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=2)
    start = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                 on_date=_d(0))
    wid = _row(start)["work_item_id"]
    day2 = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                on_date=_d(1), work_item_id=wid)
    _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
         on_date=_d(2), work_item_id=wid)            # day 3 - pending
    req = _requests(db, a["emp"].id)[0]

    client.post(f"{CR}/{req.id}/reject", headers=h["header"], json={})

    for res in (start, day2):
        got = _get(client, a["header"], res.json()["id"])
        assert len(got["tasks"]) == 1
        assert got["tasks"][0]["work_item_id"] == wid
        assert got["tasks"][0]["continuation_approval_status"] is None
        assert got["status"] == "draft"


# ==========================================================================
# 10. the Fri-Thu weekly foundation is unchanged
# ==========================================================================
def test_weekly_confinement_is_unchanged(client, team):
    """Non-regression: an item started in one reporting week is not offered in
    the next one - approval lifecycle or no approval lifecycle."""
    a, pm = team["author"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=3)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))

    this_cycle_friday = compute_week_bounds(TODAY)[0]
    assert compute_week_bounds(_d(0)) != compute_week_bounds(this_cycle_friday)

    assert _open_task(client, a["header"], report_date=_d(6),
                      work_item_id=wid) is not None       # own week: offered
    assert _open_task(client, a["header"], report_date=this_cycle_friday,
                      work_item_id=wid) is None           # next week: not


# ==========================================================================
# 11. TASK_WITH_QUANTITY is untouched by the whole lifecycle
# ==========================================================================
def test_quantity_task_is_never_gated_or_stamped(client, team, db):
    a, pm = team["author"], team["pm"]
    _, sub = _quantity_sub(client, pm, period=1)
    start = _post(client, a["header"], on_date=_d(0), tasks=[
        _task(a["project"].id, sub["id"], pages_count=10),
    ])
    wid = _row(start)["work_item_id"]

    # Well past a 1-day allowance in work days AND past the calendar due date -
    # and still ordinary work, because it is not lump-sum.
    res = _post(client, a["header"], on_date=_d(3), tasks=[
        _task(a["project"].id, sub["id"], work_item_id=wid, pages_count=10),
    ])
    row = _row(res)
    assert row["continuation_request_id"] is None
    assert row["continuation_approval_status"] is None
    assert _requests(db, a["emp"].id) == []

    # Completion is not blocked either - there is no approval to wait for.
    done = client.patch(f"{BASE}/tasks/{row['id']}/completion", headers=a["header"],
                        json={"is_completed": True})
    assert done.status_code == 200, done.text


# ==========================================================================
# 12. THE CORRECTION: a pending continuation blocks ONE ACTIVITY's completion,
#     never the report's submission.
#
# The old behaviour raised 422 out of the report save the moment the completion
# checkbox was ticked on an activity whose continuation was undecided. That
# aborted the WHOLE save - every other activity on the report with it - and
# rolled back the very request that would have told the Project Head. These
# tests pin the two rules apart: "this activity cannot be marked complete yet"
# is enforced; "this report cannot be submitted" is not.
# ==========================================================================
def _uuid_of(value):
    import uuid as _uuid

    return _uuid.UUID(str(value))


def _mixed(client, team, *, period=1, tick_ls=True, extra=0, expect=201):
    """A report on _d(2) carrying `extra` + 1 ordinary daily activities and one
    lump-sum continuation past its allowance."""
    a, pm = team["author"], team["pm"]
    _, ls = _lumpsum_sub(client, pm, period=period)
    dailies = [_daily_sub(client, pm, name=f"Daily{i}")[1] for i in range(extra + 1)]
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=ls["id"], on_date=_d(0))
    tasks = [
        _task(a["project"].id, d["id"], pages_count=40, minutes_spent=60)
        for d in dailies
    ]
    tasks.append(_task(a["project"].id, ls["id"], work_item_id=wid,
                       is_completed=tick_ls, minutes_spent=90))
    res = _post(client, a["header"], on_date=_d(2), tasks=tasks, expect=expect)
    return res, {"ls": ls, "dailies": dailies, "wid": wid}


def test_case_a_normal_activity_only_submits(client, team, db):
    """Case A - nothing about this correction may touch an ordinary report."""
    a, pm = team["author"], team["pm"]
    _, daily = _daily_sub(client, pm)
    res = _post(client, a["header"], on_date=_d(2), tasks=[
        _task(a["project"].id, daily["id"], pages_count=40, minutes_spent=60),
    ])
    assert _submit(client, a["header"], res.json()["id"])["status"] == "submitted"
    assert _requests(db, a["emp"].id) == []


def test_case_b_lumpsum_within_allowance_submits_and_completes(client, team, db):
    """Case B - inside its allowed duration a lump-sum activity is ordinary work,
    completion checkbox included."""
    a, pm = team["author"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=3)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    res = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
               on_date=_d(1), work_item_id=wid, is_completed=True)
    assert _row(res)["continuation_approval_status"] is None
    assert _submit(client, a["header"], res.json()["id"])["status"] == "submitted"
    assert _requests(db, a["emp"].id) == []
    assert db.get(WorkItem, _uuid_of(wid)).completed_on == _d(1)


def test_case_c_pending_continuation_alone_still_submits(client, team, db):
    """Case C - the report is submitted; only the continuation waits."""
    a, pm = team["author"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=1)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    res = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
               on_date=_d(2), work_item_id=wid, is_completed=True)

    got = _submit(client, a["header"], res.json()["id"])
    assert got["status"] == "submitted"
    assert got["tasks"][0]["continuation_approval_status"] == "pending"
    # The tick is honoured: the employee finished the activity and the report
    # says so. Only the continuation's acceptance is still the Head's to decide.
    assert got["tasks"][0]["row_is_completed"] is True
    assert db.get(WorkItem, _uuid_of(wid)).completed_on == _d(2)
    assert len(_requests(db, a["emp"].id)) == 1


def test_case_d_mixed_report_submits_with_only_the_ls_row_pending(client, team, db):
    """Case D - one ordinary activity alongside a ticked pending continuation.
    The ordinary row is submitted normally and keeps its own numbers; only the
    lump-sum row is pending."""
    a = team["author"]
    res, ids = _mixed(client, team, extra=0)

    got = _submit(client, a["header"], res.json()["id"])
    assert got["status"] == "submitted"
    assert len(got["tasks"]) == 2
    assert got["total_minutes"] == 60 + 90

    by_sub = {t["sub_activity_id"]: t for t in got["tasks"]}
    for d in ids["dailies"]:
        row = by_sub[d["id"]]
        assert row["continuation_approval_status"] is None
        assert row["pages_count"] == 40
        # Numeric benchmark output is untouched by the neighbouring continuation.
        assert row["benchmark_status"] is not None
    assert by_sub[ids["ls"]["id"]]["continuation_approval_status"] == "pending"
    assert len(_requests(db, a["emp"].id)) == 1


def test_case_e_second_ordinary_activity_alongside_pending_continuation_rejected(
    client, team, db
):
    """Case E - a SECOND ordinary activity alongside the pending continuation
    would make three activity rows on one report, which the universal
    maximum-two-activities rule now rejects outright (a separate, report-
    capacity rule from continuation approval — see _mixed's extra=1 shape)."""
    res, _ids = _mixed(client, team, extra=1, expect=422)
    assert "maximum of 2 activities" in res.json()["error"]["message"]


def test_case_f_pending_continuation_beside_a_completed_activity_submits(
    client, team, db
):
    """Case F - another task activity completed on the same report. BOTH
    completions are honoured, including the lump-sum one whose continuation is
    still pending, and neither decides whether the report submits."""
    a, pm = team["author"], team["pm"]
    _, ls = _lumpsum_sub(client, pm, period=1)
    _, qty = _quantity_sub(client, pm, period=1)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=ls["id"], on_date=_d(0))

    res = _post(client, a["header"], on_date=_d(2), tasks=[
        _task(a["project"].id, qty["id"], pages_count=100, is_completed=True,
              minutes_spent=60),
        _task(a["project"].id, ls["id"], work_item_id=wid, is_completed=True,
              minutes_spent=90),
    ])
    got = _submit(client, a["header"], res.json()["id"])
    assert got["status"] == "submitted"
    by_sub = {t["sub_activity_id"]: t for t in got["tasks"]}
    assert by_sub[qty["id"]]["row_is_completed"] is True
    assert by_sub[ls["id"]]["row_is_completed"] is True
    assert by_sub[ls["id"]]["continuation_approval_status"] == "pending"
    assert db.get(WorkItem, _uuid_of(wid)).completed_on == _d(2)


def test_head_is_notified_when_the_mixed_report_is_saved(client, team, db):
    """The notification the old 422 destroyed: the save now commits, so the
    reviewer request exists and is routed to the project's Head, at the reviewer
    destination - not the employee's report."""
    from app.modules.notifications.models import Notification

    a, h = team["author"], team["head"]
    _mixed(client, team, extra=0)
    req = _requests(db, a["emp"].id)[0]

    notes = db.execute(
        select(Notification).where(
            Notification.user_id == h["user"].id,
            Notification.type == "continuation_requested",
        )
    ).scalars().all()
    assert len(notes) == 1
    assert notes[0].target_url == f"/lump-sum-activity?queue=pending&id={req.id}"


def test_approval_of_a_mixed_report_leaves_everything_else_alone(client, team, db):
    """The report stays submitted, the ordinary rows stay exactly as they were,
    and the approved row rides the SAME work item with no fresh allowance."""
    a, h = team["author"], team["head"]
    res, ids = _mixed(client, team, extra=0)
    report_id = res.json()["id"]
    _submit(client, a["header"], report_id)
    req = _requests(db, a["emp"].id)[0]
    item_before = db.get(WorkItem, _uuid_of(ids["wid"]))
    before = (item_before.started_on, item_before.due_date, item_before.target_days)

    ok = client.post(f"{CR}/{req.id}/approve", headers=h["header"], json={})
    assert ok.status_code == 200, ok.text

    got = _get(client, a["header"], report_id)
    assert got["status"] == "submitted"
    assert len(got["tasks"]) == 2
    assert got["total_minutes"] == 60 + 90
    by_sub = {t["sub_activity_id"]: t for t in got["tasks"]}
    assert by_sub[ids["ls"]["id"]]["continuation_approval_status"] == "approved"
    for d in ids["dailies"]:
        assert by_sub[d["id"]]["continuation_approval_status"] is None

    db.expire_all()
    item = db.get(WorkItem, _uuid_of(ids["wid"]))
    assert (item.started_on, item.due_date, item.target_days) == before
    assert db.execute(
        select(WorkItem).where(WorkItem.employee_id == a["emp"].id)
    ).scalars().all() == [item]


def test_rejection_of_a_mixed_report_keeps_a_visible_rejected_record(client, team, db):
    """Rejection withdraws the unaccepted rows but must not erase the employee's
    history of having asked. The report survives, the ordinary rows survive, and
    the report carries a rejected-continuation record naming the activity, the
    reviewer and the reason."""
    a, h = team["author"], team["head"]
    res, ids = _mixed(client, team, extra=0)
    report_id = res.json()["id"]
    _submit(client, a["header"], report_id)
    req = _requests(db, a["emp"].id)[0]

    out = client.post(f"{CR}/{req.id}/reject", headers=h["header"],
                      json={"comment": "not justified"})
    assert out.status_code == 200, out.text

    got = _get(client, a["header"], report_id)
    assert got["status"] == "submitted"          # it still stands on its own work
    assert {t["sub_activity_id"] for t in got["tasks"]} == {
        d["id"] for d in ids["dailies"]
    }
    assert got["total_minutes"] == 60            # the rejected minutes are gone

    rejected = got["rejected_continuations"]
    assert len(rejected) == 1
    assert rejected[0]["request_id"] == str(req.id)
    assert rejected[0]["sub_activity_name"] == ids["ls"]["name"]
    assert rejected[0]["continuation_date"] == _d(2).isoformat()
    assert rejected[0]["reviewer_name"] == h["emp"].full_name
    assert rejected[0]["decision_comment"] == "not justified"


def test_rejected_record_is_not_an_approved_activity(client, team, db):
    """The record is history, not work: it is not in `tasks`, contributes no
    minutes, and the activity still cannot be continued."""
    a, h = team["author"], team["head"]
    res, ids = _mixed(client, team, tick_ls=False)
    _submit(client, a["header"], res.json()["id"])
    req = _requests(db, a["emp"].id)[0]
    client.post(f"{CR}/{req.id}/reject", headers=h["header"], json={})

    got = _get(client, a["header"], res.json()["id"])
    assert all(t["sub_activity_id"] != ids["ls"]["id"] for t in got["tasks"])
    assert len(got["rejected_continuations"]) == 1
    blocked = _one(client, a["header"], project_id=a["project"].id,
                   sub_id=ids["ls"]["id"], on_date=_d(3),
                   work_item_id=ids["wid"], expect=403)
    assert "rejected" in blocked.json()["error"]["message"].lower()


def test_report_list_does_not_carry_the_rejected_record(client, team, db):
    """Detail-only: the list must not pay for a query it never renders."""
    a, h = team["author"], team["head"]
    res, _ids = _mixed(client, team, tick_ls=False)
    _submit(client, a["header"], res.json()["id"])
    req = _requests(db, a["emp"].id)[0]
    client.post(f"{CR}/{req.id}/reject", headers=h["header"], json={})

    listed = client.get(BASE, headers=a["header"],
                        params={"employee_id": str(a["emp"].id)}).json()
    row = next(r for r in listed["items"] if r["id"] == res.json()["id"])
    assert row["rejected_continuations"] == []


# ==========================================================================
# 13. the mandatory count requirement (test_lumpsum_count_field.py) reaches
#     continuation rows too, and disturbs nothing about the lifecycle itself.
# ==========================================================================
def test_5_continuation_lifecycle_is_unchanged_by_the_mandatory_count(
    client, team, db
):
    """5. Existing LS continuation flow → unchanged. Every row in this file's
    scenarios now carries a count (see `_task`'s default), and the pending ->
    approve handshake still runs exactly as before: same request, same work
    item, same frozen deadline."""
    a, h, pm = team["author"], team["head"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=1)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))

    res = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
               on_date=_d(2), work_item_id=wid)
    row = _row(res)
    assert row["continuation_approval_status"] == "pending"

    req = _requests(db, a["emp"].id)[0]
    ok = client.post(f"{CR}/{req.id}/approve", headers=h["header"], json={})
    assert ok.status_code == 200, ok.text

    got = _get(client, a["header"], res.json()["id"])
    assert got["tasks"][0]["continuation_approval_status"] == "approved"
    assert got["tasks"][0]["work_item_id"] == wid


def test_a_continuation_row_still_needs_its_own_count(client, team, db):
    """The mandatory rule is per-row, not per-activity: a continuation day
    that omits the count is rejected exactly like a fresh LS row would be."""
    a, pm = team["author"], team["pm"]
    _, sub = _lumpsum_sub(client, pm, period=1)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))

    res = _one(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
               on_date=_d(2), work_item_id=wid, count_field=None, count_value=None,
               expect=422)
    assert "count" in res.json()["error"]["message"].lower()
