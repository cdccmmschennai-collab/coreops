"""Project Summary (Phase 6) — the aggregate progress payload behind the tab.

What the Summary is, and is not:

  It reports one row per tag-counted sub-activity ACTUALLY reported on the
  project: parent Activity, Sub-Activity, reported / scope, remaining. Every row
  measures against the same estimate independently, so the rows never sum to a
  project total.

  It carries no employee, no date and no per-report line. Phase 6 deliberately
  stops at the aggregate; detailed weekly records are a separate surface.

The numbers come from the same consumption query the tag cap enforces with
(tag_progress._consumption_stmt), so "Summary says 700/1200" and "the cap
refuses the 501st tag" are guaranteed to be the same fact — see
test_summary_agrees_with_the_cap.
"""
from datetime import date, timedelta

import pytest

from app.modules.activity_master.models import ActivityMaster
from app.modules.projects import tag_progress
from app.modules.projects.models import ProjectMember, ProjectStatus
from app.modules.users.models import UserRole

BASE = "/api/v1/projects"
REPORTS = "/api/v1/work-reports"

# Relative to today: a report date in the future is rejected outright, so fixed
# literals would start failing the day after they were written.
TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


@pytest.fixture()
def summary_project(db, make_project, make_user, make_employee, client):
    """A TAG_BASED project scoped to 1200 with the brief's three activities.

    Two distinct parent Activities (DEMOLITION, FMTL) and a third (MTL) so the
    Activity column has something real to prove, plus a docs sub-activity that
    must never appear in a tag Summary.
    """
    project = make_project(code="SUM-1", status=ProjectStatus.active)
    project.scope_type = "TAG_BASED"
    project.estimated_tag_count = 1200
    project.tag_scope_status = "BASELINED"
    project.tag_scope_revision = 1
    db.add(project)

    demolition = ActivityMaster(name="DEMOLITION", level="activity")
    fmtl = ActivityMaster(name="FMTL", level="activity")
    mtl = ActivityMaster(name="MTL", level="activity")
    db.add_all([demolition, fmtl, mtl])
    db.commit()

    def sub(name: str, parent, unit: str = "tags"):
        row = ActivityMaster(
            name=name, level="sub_activity", parent_id=parent.id,
            benchmark_type="NUMERIC_DAILY", benchmark_value=250,
            relevant_count_field=unit,
        )
        db.add(row)
        return row

    rework = sub("DEMOLITION-REWORK", demolition)
    spir = sub("FMTL DATA POPULATION-SPIR DOC.NO/SPIR TAG NO", fmtl)
    photo = sub("MTL-ASSET PHOTO DATA POPULATION", mtl)
    docs = sub("FMTL-DOC COLLECTION", fmtl, unit="docs")
    db.commit()

    def employee(email: str, code: str):
        user = make_user(email, "password123", UserRole.employee)
        emp = make_employee(employee_code=code, user_id=user.id)
        db.add(ProjectMember(project_id=project.id, employee_id=emp.id))
        db.commit()
        res = client.post(
            "/api/v1/auth/login", json={"identifier": email, "password": "password123"}
        )
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    return {
        "project": project,
        "demolition": demolition,
        "fmtl": fmtl,
        "mtl": mtl,
        "rework": rework,
        "spir": spir,
        "photo": photo,
        "docs": docs,
        "emp_a": employee("suma@x.com", "SUM-A"),
        "emp_b": employee("sumb@x.com", "SUM-B"),
    }


def _report(client, headers, project, sub, tags, *, day=TODAY, docs=None):
    task = {
        "project_id": str(project.id),
        "sub_activity_id": str(sub.id),
        "minutes_spent": 60,
        "description": "work",
    }
    if tags is not None:
        task["tags_count"] = tags
    if docs is not None:
        task["docs_count"] = docs
    res = client.post(
        REPORTS,
        json={"report_date": day, "day_status": "work_at_office", "tasks": [task]},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res


def _summary(client, headers, project):
    res = client.get(f"{BASE}/{project.id}/summary", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _by_sub(payload) -> dict:
    return {r["sub_activity_name"]: r for r in payload["tag_progress"]}


# ---------- the columns the tab renders ----------
def test_every_row_carries_its_parent_activity(client, summary_project):
    """The Activity column exists as its own field, from the real Activity
    Master edge — not sliced out of the sub-activity name."""
    s = summary_project
    _report(client, s["emp_a"], s["project"], s["rework"], 700)
    _report(client, s["emp_b"], s["project"], s["spir"], 400, day=YESTERDAY)

    rows = _by_sub(_summary(client, s["emp_a"], s["project"]))
    assert rows["DEMOLITION-REWORK"]["activity_name"] == "DEMOLITION"
    assert rows["DEMOLITION-REWORK"]["activity_id"] == str(s["demolition"].id)
    spir = rows["FMTL DATA POPULATION-SPIR DOC.NO/SPIR TAG NO"]
    assert spir["activity_name"] == "FMTL"
    assert spir["activity_id"] == str(s["fmtl"].id)


def test_activity_and_sub_activity_stay_separate_fields(client, summary_project):
    """Two columns, never one merged label."""
    s = summary_project
    _report(client, s["emp_a"], s["project"], s["rework"], 700)

    row = _by_sub(_summary(client, s["emp_a"], s["project"]))["DEMOLITION-REWORK"]
    assert row["activity_name"] == "DEMOLITION"
    assert row["sub_activity_name"] == "DEMOLITION-REWORK"
    assert row["activity_name"] != row["sub_activity_name"]


def test_reported_and_scope_are_correct(client, summary_project):
    s = summary_project
    _report(client, s["emp_a"], s["project"], s["rework"], 700)

    row = _by_sub(_summary(client, s["emp_a"], s["project"]))["DEMOLITION-REWORK"]
    assert row["reported_tags"] == 700
    assert row["estimated_tag_count"] == 1200


def test_remaining_is_scope_minus_reported(client, summary_project):
    s = summary_project
    _report(client, s["emp_a"], s["project"], s["rework"], 700)

    row = _by_sub(_summary(client, s["emp_a"], s["project"]))["DEMOLITION-REWORK"]
    assert row["remaining_tags"] == 500


def test_reported_accumulates_across_employees_and_days(client, summary_project):
    """One sub-activity's progress is the project's, not one person's."""
    s = summary_project
    _report(client, s["emp_a"], s["project"], s["rework"], 400)
    _report(client, s["emp_b"], s["project"], s["rework"], 300, day=YESTERDAY)

    row = _by_sub(_summary(client, s["emp_a"], s["project"]))["DEMOLITION-REWORK"]
    assert row["reported_tags"] == 700
    assert row["remaining_tags"] == 500


# ---------- the independence rule ----------
def test_sub_activities_progress_independently_through_the_same_scope(
    client, summary_project
):
    """The brief's table: 700, 400 and 40 against 1200 each. They are three
    separate progressions, never 1140/1200 of a shared pool."""
    s = summary_project
    _report(client, s["emp_a"], s["project"], s["rework"], 700)
    _report(client, s["emp_b"], s["project"], s["spir"], 400)
    _report(client, s["emp_a"], s["project"], s["photo"], 40, day=YESTERDAY)

    rows = _by_sub(_summary(client, s["emp_a"], s["project"]))
    assert (rows["DEMOLITION-REWORK"]["reported_tags"],
            rows["DEMOLITION-REWORK"]["remaining_tags"]) == (700, 500)
    spir = rows["FMTL DATA POPULATION-SPIR DOC.NO/SPIR TAG NO"]
    assert (spir["reported_tags"], spir["remaining_tags"]) == (400, 800)
    assert (rows["MTL-ASSET PHOTO DATA POPULATION"]["reported_tags"],
            rows["MTL-ASSET PHOTO DATA POPULATION"]["remaining_tags"]) == (40, 1160)

    # Every row measures against the whole scope; none of them consumed another's.
    assert {r["estimated_tag_count"] for r in rows.values()} == {1200}


def test_one_sub_activity_at_full_scope_leaves_the_others_untouched(
    client, summary_project
):
    s = summary_project
    _report(client, s["emp_a"], s["project"], s["rework"], 1200)
    _report(client, s["emp_b"], s["project"], s["spir"], 400)

    rows = _by_sub(_summary(client, s["emp_a"], s["project"]))
    assert rows["DEMOLITION-REWORK"]["remaining_tags"] == 0
    assert rows["FMTL DATA POPULATION-SPIR DOC.NO/SPIR TAG NO"]["remaining_tags"] == 800


# ---------- the blank-Remaining regression (spec §9) ----------
@pytest.mark.parametrize("reported,expected_remaining", [
    (40, 1160),     # the row that rendered blank
    (1, 1199),
    (1199, 1),
    (1200, 0),
])
def test_remaining_is_always_a_real_number(
    client, summary_project, reported, expected_remaining
):
    """Remaining is never null, never absent and never needs client arithmetic.

    The reported blank cell was a rendering fault, not a payload one, but the
    contract is what stops it coming back: every row ships remaining_tags as a
    plain non-negative int, so there is nothing for a client to compute (and so
    nothing for it to compute into undefined/NaN).
    """
    s = summary_project
    _report(client, s["emp_a"], s["project"], s["photo"], reported)

    row = _by_sub(_summary(client, s["emp_a"], s["project"]))["MTL-ASSET PHOTO DATA POPULATION"]
    assert row["remaining_tags"] == expected_remaining


def test_remaining_never_blank_for_the_reported_forty(client, summary_project):
    """40 / 1200 must read 1160 — the exact row from the bug report."""
    s = summary_project
    _report(client, s["emp_a"], s["project"], s["photo"], 40)

    row = _by_sub(_summary(client, s["emp_a"], s["project"]))["MTL-ASSET PHOTO DATA POPULATION"]
    assert row["reported_tags"] == 40
    assert row["remaining_tags"] == 1160
    assert isinstance(row["remaining_tags"], int)


def test_no_row_has_a_missing_or_negative_remaining(client, summary_project):
    """Structural guard across the whole payload, so a future row shape cannot
    quietly ship a null into the Remaining column."""
    s = summary_project
    _report(client, s["emp_a"], s["project"], s["rework"], 700)
    _report(client, s["emp_b"], s["project"], s["spir"], 400)
    _report(client, s["emp_a"], s["project"], s["photo"], 40, day=YESTERDAY)

    payload = _summary(client, s["emp_a"], s["project"])
    assert payload["tag_progress"]
    for row in payload["tag_progress"]:
        for field in ("reported_tags", "estimated_tag_count", "remaining_tags"):
            assert field in row, field
            assert row[field] is not None, field
            assert isinstance(row[field], int), field
            assert row[field] >= 0, field
        assert row["remaining_tags"] == row["estimated_tag_count"] - row["reported_tags"]
        assert row["sub_activity_name"]
        assert row["sub_activity_id"]


def test_remaining_floors_at_zero_when_history_exceeds_a_reduced_scope(
    client, db, summary_project
):
    """Legacy data above a later-reduced estimate reads 0 remaining, never
    negative — and reported_tags keeps telling the truth about the overrun."""
    s = summary_project
    _report(client, s["emp_a"], s["project"], s["rework"], 700)
    s["project"].estimated_tag_count = 500
    db.add(s["project"])
    db.commit()

    row = _by_sub(_summary(client, s["emp_a"], s["project"]))["DEMOLITION-REWORK"]
    assert row["reported_tags"] == 700       # not rewritten
    assert row["estimated_tag_count"] == 500
    assert row["remaining_tags"] == 0        # not -200


# ---------- what never appears ----------
def test_a_non_tag_sub_activity_never_appears(client, summary_project):
    """Participation is derived from relevant_count_field == 'tags'. A docs
    activity is not part of tag scope, with or without an Activity Master flag."""
    s = summary_project
    _report(client, s["emp_a"], s["project"], s["rework"], 700)
    _report(client, s["emp_b"], s["project"], s["docs"], None, docs=900)

    assert "FMTL-DOC COLLECTION" not in _by_sub(_summary(client, s["emp_a"], s["project"]))


def test_summary_carries_no_employee_or_date_detail(client, summary_project):
    """Phase 6 stops at the aggregate. No employee, no date, no per-report line
    anywhere in the payload."""
    s = summary_project
    _report(client, s["emp_a"], s["project"], s["rework"], 700)

    payload = _summary(client, s["emp_a"], s["project"])
    banned = ("employee", "date", "contribution", "report_id", "name_of")
    for row in payload["tag_progress"]:
        for key in row:
            assert not any(b in key for b in banned), key


def test_there_is_no_drill_down_endpoint(client, summary_project):
    """The employee/date drill-down was cancelled: the nested route must not
    exist, so no client can reach employee-level data through Summary."""
    s = summary_project
    res = client.get(
        f"{BASE}/{s['project'].id}/summary/sub-activities/{s['rework'].id}",
        headers=s["emp_a"],
    )
    assert res.status_code == 404, res.text


# ---------- agreement with the cap ----------
def test_summary_agrees_with_the_cap(client, db, summary_project):
    """The Summary's reported/remaining IS the cap's, by construction.

    Summary says 700 / 1200 with 500 remaining, so the cap accepts 500 more and
    refuses 501. One shared consumption query means these can never disagree.
    """
    s = summary_project
    _report(client, s["emp_a"], s["project"], s["rework"], 700)

    row = _by_sub(_summary(client, s["emp_a"], s["project"]))["DEMOLITION-REWORK"]
    assert (row["reported_tags"], row["remaining_tags"]) == (700, 500)
    assert tag_progress.recorded_tags(db, s["project"].id, s["rework"].id) == 700
    assert tag_progress.remaining_tags(db, s["project"], s["rework"]) == 500

    over = client.post(
        REPORTS,
        json={"report_date": YESTERDAY, "day_status": "work_at_office", "tasks": [{
            "project_id": str(s["project"].id),
            "sub_activity_id": str(s["rework"].id),
            "minutes_spent": 60, "description": "w", "tags_count": 501,
        }]},
        headers=s["emp_b"],
    )
    assert over.status_code == 422, over.text
    _report(client, s["emp_b"], s["project"], s["rework"], 500, day=YESTERDAY)


# ---------- the three empty states ----------
def test_a_normal_project_reports_no_tag_progress(client, db, summary_project):
    """scope_type NONE: no rows, and the payload says why — the tab shows "this
    project does not use tag-based scope", never 0 / 0."""
    s = summary_project
    _report(client, s["emp_a"], s["project"], s["rework"], 700)
    s["project"].scope_type = "NONE"
    db.add(s["project"])
    db.commit()

    payload = _summary(client, s["emp_a"], s["project"])
    assert payload["scope_type"] == "NONE"
    assert payload["tag_progress"] == []


def test_a_tag_project_without_an_estimate_reports_no_progress(
    client, db, summary_project
):
    """TAG_BASED with a null estimate: no rows and no invented capacity. There
    is nothing to measure against, so no percentage is fabricated."""
    s = summary_project
    _report(client, s["emp_a"], s["project"], s["rework"], 700)
    s["project"].estimated_tag_count = None
    s["project"].tag_scope_status = None
    db.add(s["project"])
    db.commit()

    payload = _summary(client, s["emp_a"], s["project"])
    assert payload["scope_type"] == "TAG_BASED"
    assert payload["estimated_tag_count"] is None
    assert payload["tag_progress"] == []


def test_a_scoped_project_with_no_reports_lists_nothing(client, summary_project):
    """Scope configured, nothing reported: an empty list, NOT a 0/1200 row for
    every tags sub-activity in Activity Master. The catalogue is not this
    project's plan of work."""
    s = summary_project
    payload = _summary(client, s["emp_a"], s["project"])
    assert payload["estimated_tag_count"] == 1200
    assert payload["tag_progress"] == []


# ---------- visibility ----------
def test_every_authorized_project_viewer_sees_the_summary(client, summary_project):
    """Aggregate progress is project context, not management data. An ordinary
    assigned member reads the same payload a PM does."""
    s = summary_project
    _report(client, s["emp_a"], s["project"], s["rework"], 700)

    member = _summary(client, s["emp_b"], s["project"])
    assert _by_sub(member)["DEMOLITION-REWORK"]["remaining_tags"] == 500


def test_a_project_manager_sees_the_summary(client, summary_project, make_user, login):
    s = summary_project
    _report(client, s["emp_a"], s["project"], s["rework"], 700)
    make_user("sumpm@x.com", "password123", UserRole.project_manager)
    pm = login("sumpm@x.com")

    assert _by_sub(_summary(client, pm, s["project"]))["DEMOLITION-REWORK"][
        "reported_tags"
    ] == 700


def test_an_unassigned_employee_still_cannot_read_the_summary(
    client, db, summary_project, make_user, make_employee
):
    """Summary is open to every AUTHORIZED viewer — the project read rule is
    unchanged, not widened."""
    s = summary_project
    user = make_user("outsider@x.com", "password123", UserRole.employee)
    make_employee(employee_code="SUM-OUT", user_id=user.id)
    db.commit()
    res = client.post(
        "/api/v1/auth/login",
        json={"identifier": "outsider@x.com", "password": "password123"},
    )
    outsider = {"Authorization": f"Bearer {res.json()['access_token']}"}

    assert client.get(f"{BASE}/{s['project'].id}/summary", headers=outsider).status_code == 403
