"""Lump-sum allowed duration is spent in WORK DAYS, not calendar days.

The approved rule: a lump-sum (NON_QUANTITATIVE) activity's allowed duration is
the number of distinct report dates on which the employee actually worked on
that activity. Days with no entry for it consume nothing, so

    day 1  worked  ->  1 of 2 used
    (three calendar days pass with no entry)
    day 2  worked  ->  2 of 2 used, still within the allowed duration
    day 3  worked  ->  blocked until the Project Head approves a continuation

Every date here sits inside ONE Friday-Thursday cycle in the past, so the
scenarios are ones an employee can actually reach through the report form (open
tasks are only suggested inside their own cycle) and never run into the
"report date cannot be in the future" rule.

TASK_WITH_QUANTITY is deliberately covered too: it must keep the old calendar
due-date behaviour and never be gated.
"""
from datetime import date, timedelta

import pytest

from app.core.config import settings
from app.modules.activity_master.service import compute_week_bounds
from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole
from app.modules.work_reports.models import WorkItem
from app.modules.work_reports.work_items import (
    compute_due_date,
    lumpsum_allowance_exhausted,
    lumpsum_days_over,
    lumpsum_lifecycle,
)

BASE = "/api/v1/work-reports"
OPEN_TASKS = "/api/v1/work-reports/open-tasks"
CR = "/api/v1/continuation-requests"
TODAY = date.today()
# The PREVIOUS Friday-Thursday cycle: seven consecutive days that are all in the
# past whatever weekday the suite runs on, and all inside the editable report
# window (current + previous month).
PREV_FRI = compute_week_bounds(TODAY)[0] - timedelta(days=7)


def _d(offset: int) -> date:
    """A date inside the previous cycle: _d(0) is its Friday, _d(6) its Thursday."""
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


def _lumpsum_sub(client, admin, *, name="Lumpsum", period=2):
    """A lump-sum sub-activity: a task benchmark with NO relevant_count_field."""
    a = client.post(
        "/api/v1/activity-master/activities",
        json={"name": f"Activity {name}"}, headers=admin,
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


def _quantity_sub(client, admin, *, name="Quantity", period=2):
    a = client.post(
        "/api/v1/activity-master/activities",
        json={"name": f"Activity {name}"}, headers=admin,
    ).json()
    return a, client.post(
        f"/api/v1/activity-master/activities/{a['id']}/sub-activities",
        json={"name": name, "benchmark_type": "TASK_WITH_QUANTITY",
              "relevant_count_field": "pages", "benchmark_value": 100,
              "benchmark_period_days": period},
        headers=admin,
    ).json()


def _post(client, header, *, project_id, sub_id, on_date, work_item_id=None,
          is_completed=False, expect=201):
    task = {"project_id": str(project_id), "description": "work",
            "sub_activity_id": sub_id, "is_completed": is_completed}
    if work_item_id is not None:
        task["work_item_id"] = str(work_item_id)
    res = client.post(BASE, headers=header, json={
        "report_date": on_date.isoformat(), "day_status": "work_at_office",
        "location": "chennai", "tasks": [task],
    })
    assert res.status_code == expect, res.text
    return res


def _start(client, header, *, project_id, sub_id, on_date):
    return _post(client, header, project_id=project_id, sub_id=sub_id,
                 on_date=on_date).json()["tasks"][0]["work_item_id"]


def _open_task(client, header, *, report_date, work_item_id):
    ot = client.get(OPEN_TASKS, headers=header,
                    params={"report_date": report_date.isoformat()}).json()
    return next((t for t in ot["items"] if t["work_item_id"] == work_item_id), None)


# --------------------------------------------------------------------------
# the pure rule
# --------------------------------------------------------------------------
def test_allowance_is_spent_by_work_days_not_calendar_days():
    # A 2-day lump-sum: one work day used still leaves today; two uses it up.
    assert lumpsum_allowance_exhausted(0, 2) is False
    assert lumpsum_allowance_exhausted(1, 2) is False
    assert lumpsum_allowance_exhausted(2, 2) is True
    # A blank/zero benchmark period still grants exactly one work day.
    assert lumpsum_allowance_exhausted(0, 0) is False
    assert lumpsum_allowance_exhausted(1, 0) is True


def test_lumpsum_lifecycle_counts_remaining_work_days():
    assert lumpsum_lifecycle(0, 3).value == "IN_PROGRESS"
    assert lumpsum_lifecycle(1, 3).value == "IN_PROGRESS"
    assert lumpsum_lifecycle(2, 3).value == "DUE_TODAY"   # today is the last one
    assert lumpsum_lifecycle(3, 3).value == "OVERDUE"     # spent
    assert lumpsum_lifecycle(0, 1).value == "DUE_TODAY"


def test_lumpsum_days_over_only_counts_days_beyond_the_allowance():
    assert lumpsum_days_over(1, 2) == 0
    assert lumpsum_days_over(2, 2) == 0   # spent, but nothing taken beyond it yet
    assert lumpsum_days_over(4, 2) == 2   # two approved continuation days used


# --------------------------------------------------------------------------
# 2-day lump-sum
# --------------------------------------------------------------------------
def test_two_day_lumpsum_consecutive_days(flag_on, client, author, pm_header, db):
    """Day 1 and day 2 back to back; the third work day needs approval."""
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=2)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    # Day 2 - the last day of the allowed duration.
    _post(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
          on_date=_d(1), work_item_id=wid, expect=201)
    # Day 3 - allowance spent.
    res = _post(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                on_date=_d(2), work_item_id=wid, expect=403)
    assert "allowed duration" in res.json()["error"]["message"].lower()


def test_two_day_lumpsum_with_skipped_calendar_days(flag_on, client, author, pm_header, db):
    """The rule that changed: three calendar days pass with no entry, and the
    next entry is still only day 2 of 2 - even though the item's frozen calendar
    due date is by then in the past."""
    import uuid as _uuid

    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=2)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))

    item = db.get(WorkItem, _uuid.UUID(wid))
    assert item.due_date == compute_due_date(db, _d(0), 2)
    assert item.due_date < _d(4)          # the calendar deadline has passed ...

    # ... and it makes no difference: this is the second WORK day.
    _post(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
          on_date=_d(4), work_item_id=wid, expect=201)
    # The next work entry after that is the one that needs approval.
    _post(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
          on_date=_d(6), work_item_id=wid, expect=403)
    # The originating history is untouched by any of this.
    db.expire_all()
    item = db.get(WorkItem, _uuid.UUID(wid))
    assert item.started_on == _d(0)
    assert item.target_days == 2
    assert item.due_date == compute_due_date(db, _d(0), 2)


def test_one_day_lumpsum_blocks_the_next_work_entry(flag_on, client, author, pm_header):
    """A 1-day lump-sum is used up by the day it starts; the next entry - however
    many calendar days later - is blocked."""
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    _post(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
          on_date=_d(2), work_item_id=wid, expect=403)


# --------------------------------------------------------------------------
# 3-day lump-sum
# --------------------------------------------------------------------------
def test_three_day_lumpsum_with_skipped_calendar_days(flag_on, client, author, pm_header):
    """Days 2 and 3 are reached across gaps; only the fourth work entry is gated."""
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=3)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    for day in (_d(2), _d(4)):            # work days 2 and 3
        _post(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
              on_date=day, work_item_id=wid, expect=201)
    _post(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
          on_date=_d(6), work_item_id=wid, expect=403)


def test_continuation_required_only_after_the_allowance_is_spent(
    flag_on, client, author, pm_header
):
    """Walk a 3-day lump-sum day by day and read the state the form shows: the
    approval prompt appears on the first work day past the allowance and not
    one day earlier."""
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=3)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))

    t = _open_task(client, a["header"], report_date=_d(1), work_item_id=wid)
    assert (t["days_used"], t["lifecycle"]) == (1, "IN_PROGRESS")
    assert t["requires_continuation_approval"] is False

    _post(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
          on_date=_d(1), work_item_id=wid, expect=201)
    t = _open_task(client, a["header"], report_date=_d(3), work_item_id=wid)
    assert (t["days_used"], t["lifecycle"]) == (2, "DUE_TODAY")  # last allowed day
    assert t["requires_continuation_approval"] is False

    _post(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
          on_date=_d(3), work_item_id=wid, expect=201)
    t = _open_task(client, a["header"], report_date=_d(5), work_item_id=wid)
    assert (t["days_used"], t["lifecycle"], t["days_overdue"]) == (3, "OVERDUE", 0)
    assert t["requires_continuation_approval"] is True
    assert t["continuation_status"] is None
    _post(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
          on_date=_d(5), work_item_id=wid, expect=403)


# --------------------------------------------------------------------------
# incomplete within the allowance / already completed
# --------------------------------------------------------------------------
def test_incomplete_within_allowance_is_suggested_and_ungated(
    flag_on, client, author, pm_header
):
    """An unfinished lump-sum with work days left is offered for continuation
    with no approval prompt, however stale its calendar due date is."""
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=3)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    t = _open_task(client, a["header"], report_date=_d(6), work_item_id=wid)
    assert t is not None
    assert t["days_used"] == 1
    assert t["lifecycle"] == "IN_PROGRESS"
    assert t["days_overdue"] == 0
    assert t["requires_continuation_approval"] is False
    assert t["continuation_request_id"] is None
    _post(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
          on_date=_d(6), work_item_id=wid, expect=201)


def test_completed_lumpsum_is_neither_suggested_nor_continuable(
    flag_on, client, author, pm_header, db
):
    """Completion ends the activity: it drops out of the suggestions and a later
    entry is refused as completed, never as a continuation-approval problem."""
    import uuid as _uuid

    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=2)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    _post(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
          on_date=_d(1), work_item_id=wid, is_completed=True, expect=201)
    assert db.get(WorkItem, _uuid.UUID(wid)).completed_on == _d(1)

    assert _open_task(client, a["header"], report_date=_d(3), work_item_id=wid) is None
    res = _post(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                on_date=_d(3), work_item_id=wid, expect=422)
    assert "already completed" in res.json()["error"]["message"].lower()


# --------------------------------------------------------------------------
# approved continuation
# --------------------------------------------------------------------------
def test_approved_continuation_unlocks_further_work_days(
    flag_on, client, author, pm_header
):
    """Once the allowance is spent the employee raises a request from the same
    state the form shows, and approval unblocks the work days after it."""
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=2)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    _post(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
          on_date=_d(2), work_item_id=wid, expect=201)      # day 2 of 2
    _post(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
          on_date=_d(4), work_item_id=wid, expect=403)      # spent

    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wid, "continuation_date": _d(4).isoformat(),
    }).json()
    assert req["status"] == "pending"
    assert client.post(f"{CR}/{req['id']}/approve", headers=pm_header,
                       json={}).status_code == 200

    _post(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
          on_date=_d(4), work_item_id=wid, expect=201)
    # Approval is permanent for the life of the item - the day after it is not
    # blocked again.
    _post(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
          on_date=_d(5), work_item_id=wid, expect=201)

    t = _open_task(client, a["header"], report_date=_d(6), work_item_id=wid)
    assert (t["days_used"], t["lifecycle"], t["days_overdue"]) == (4, "OVERDUE", 2)
    assert t["continuation_status"] == "approved"
    assert t["requires_continuation_approval"] is False


def test_request_is_refused_while_work_days_remain(flag_on, client, author, pm_header):
    """The request surface applies the same work-day rule as the save gate: with
    a day still in hand there is nothing to approve."""
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=2)
    wid = _start(client, a["header"], project_id=a["project"].id,
                 sub_id=sub["id"], on_date=_d(0))
    res = client.post(CR, headers=a["header"], json={
        "work_item_id": wid, "continuation_date": _d(4).isoformat(),
    })
    assert res.status_code == 422, res.text
    assert "still within its allowed duration" in res.json()["error"]["message"].lower()


# --------------------------------------------------------------------------
# TASK_WITH_QUANTITY is untouched by all of this
# --------------------------------------------------------------------------
def test_quantity_task_keeps_calendar_lifecycle_and_is_never_gated(
    flag_on, client, author, pm_header, db
):
    a = author()
    _, sub = _quantity_sub(client, pm_header, period=2)
    r = client.post(BASE, headers=a["header"], json={
        "report_date": _d(0).isoformat(), "day_status": "work_at_office",
        "location": "chennai",
        "tasks": [{"project_id": str(a["project"].id), "description": "work",
                   "sub_activity_id": sub["id"], "pages_count": 10}],
    })
    assert r.status_code == 201, r.text
    wid = r.json()["tasks"][0]["work_item_id"]

    # Past its calendar due date, with days skipped: still continuable, and its
    # lifecycle is still the CALENDAR one (work-day counting never applies).
    t = _open_task(client, a["header"], report_date=_d(6), work_item_id=wid)
    assert t["lifecycle"] == "OVERDUE"
    assert t["days_overdue"] > 0
    assert t["requires_continuation_approval"] is False
    res = client.post(BASE, headers=a["header"], json={
        "report_date": _d(6).isoformat(), "day_status": "work_at_office",
        "location": "chennai",
        "tasks": [{"project_id": str(a["project"].id), "description": "work",
                   "sub_activity_id": sub["id"], "work_item_id": str(wid),
                   "pages_count": 10}],
    })
    assert res.status_code == 201, res.text
