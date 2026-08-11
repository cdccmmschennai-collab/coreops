"""Project Tag Scope consumption: tag-counted work cannot exceed the project's
estimated tag scope.

The rule under test:

  A tag-based project with an estimate of N gives every tag-counted
  sub-activity N tags to work through. Within ONE sub-activity the reported
  counts accumulate across employees and days, so 500 reported by anyone leaves
  N-500 for everyone. Across DIFFERENT sub-activities they do not interact â€”
  each one gets the full N.

Participation is derived, not configured: relevant_count_field == 'tags' plus a
TAG_BASED project with an estimate. Nothing is ticked in Activity Master.
"""
from datetime import date, timedelta

import pytest

from app.modules.activity_master.models import ActivityMaster
from app.modules.projects import tag_progress
from app.modules.projects.models import ProjectMember, ProjectStatus
from app.modules.users.models import UserRole

REPORTS = "/api/v1/work-reports"

# Relative to today: a report date in the future is rejected outright, so fixed
# literals would start failing the day after they were written.
TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


@pytest.fixture()
def scoped(db, make_project, make_user, make_employee, client):
    """A TAG_BASED project scoped to 1000, one tags sub-activity, one docs
    sub-activity, and two employees assigned to the project."""
    project = make_project(code="CAP-1", status=ProjectStatus.active)
    project.scope_type = "TAG_BASED"
    project.estimated_tag_count = 1000
    project.tag_scope_status = "BASELINED"
    project.tag_scope_revision = 1
    db.add(project)

    parent = ActivityMaster(name="FMTL", level="activity")
    db.add(parent)
    db.commit()
    tags_sub = ActivityMaster(
        name="FMTL-TAG DESCRIPTION", level="sub_activity", parent_id=parent.id,
        benchmark_type="NUMERIC_DAILY", benchmark_value=250, relevant_count_field="tags",
    )
    other_tags_sub = ActivityMaster(
        name="MTL-ASSET PHOTO MERGING", level="sub_activity", parent_id=parent.id,
        benchmark_type="NUMERIC_DAILY", benchmark_value=250, relevant_count_field="tags",
    )
    docs_sub = ActivityMaster(
        name="DOC-COLLECTION", level="sub_activity", parent_id=parent.id,
        benchmark_type="NUMERIC_DAILY", benchmark_value=50, relevant_count_field="docs",
    )
    db.add_all([tags_sub, other_tags_sub, docs_sub])
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
        "tags_sub": tags_sub,
        "other_tags_sub": other_tags_sub,
        "docs_sub": docs_sub,
        "emp_a": employee("capa@x.com", "CAP-A"),
        "emp_b": employee("capb@x.com", "CAP-B"),
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
    return client.post(
        REPORTS,
        json={"report_date": day, "day_status": "work_at_office", "tasks": [task]},
        headers=headers,
    )


# ---------- the core rule ----------
def test_a_count_within_the_scope_is_accepted(client, scoped):
    res = _report(client, scoped["emp_a"], scoped["project"], scoped["tags_sub"], 500)
    assert res.status_code == 201, res.text


def test_a_count_above_the_whole_scope_is_refused(client, scoped):
    res = _report(client, scoped["emp_a"], scoped["project"], scoped["tags_sub"], 1001)
    assert res.status_code == 422, res.text
    assert "1000" in res.json()["error"]["message"]


def test_exactly_the_scope_is_allowed(client, scoped):
    res = _report(client, scoped["emp_a"], scoped["project"], scoped["tags_sub"], 1000)
    assert res.status_code == 201, res.text


def test_another_employee_is_capped_by_what_the_first_reported(client, scoped):
    """The example from the brief: A reports 500 of 1000, so B may report at
    most 500 on the same sub-activity."""
    first = _report(client, scoped["emp_a"], scoped["project"], scoped["tags_sub"], 500)
    assert first.status_code == 201, first.text

    over = _report(
        client, scoped["emp_b"], scoped["project"], scoped["tags_sub"], 501,
        day=YESTERDAY,
    )
    assert over.status_code == 422, over.text
    assert "500" in over.json()["error"]["message"]

    exact = _report(
        client, scoped["emp_b"], scoped["project"], scoped["tags_sub"], 500,
        day=YESTERDAY,
    )
    assert exact.status_code == 201, exact.text


def test_the_scope_is_exhausted_once_fully_reported(client, scoped):
    _report(client, scoped["emp_a"], scoped["project"], scoped["tags_sub"], 1000)
    res = _report(
        client, scoped["emp_b"], scoped["project"], scoped["tags_sub"], 1,
        day=YESTERDAY,
    )
    assert res.status_code == 422, res.text


# ---------- independence between sub-activities ----------
def test_each_sub_activity_gets_the_full_scope_independently(client, scoped):
    """1000 reported on one activity must take nothing away from another."""
    a = _report(client, scoped["emp_a"], scoped["project"], scoped["tags_sub"], 1000)
    assert a.status_code == 201, a.text
    b = _report(
        client, scoped["emp_b"], scoped["project"], scoped["other_tags_sub"], 1000,
        day=YESTERDAY,
    )
    assert b.status_code == 201, b.text


# ---------- what the rule does NOT touch ----------
def test_a_docs_activity_is_never_capped(client, scoped):
    res = _report(
        client, scoped["emp_a"], scoped["project"], scoped["docs_sub"], None, docs=99999
    )
    assert res.status_code == 201, res.text


def test_a_normal_project_is_unaffected(client, db, scoped):
    p = scoped["project"]
    p.scope_type = "NONE"
    db.add(p)
    db.commit()
    res = _report(client, scoped["emp_a"], p, scoped["tags_sub"], 99999)
    assert res.status_code == 201, res.text


def test_a_tag_project_with_no_estimate_is_unaffected(client, db, scoped):
    p = scoped["project"]
    p.estimated_tag_count = None
    p.tag_scope_status = None
    db.add(p)
    db.commit()
    res = _report(client, scoped["emp_a"], p, scoped["tags_sub"], 99999)
    assert res.status_code == 201, res.text


# ---------- multi-row submissions ----------
def test_two_rows_of_one_report_are_summed_before_comparing(client, scoped):
    """400 + 700 in a single report is 1100 against a 1000 scope, even though
    neither row alone exceeds it."""
    p, sub = scoped["project"], scoped["tags_sub"]
    task = lambda n: {
        "project_id": str(p.id), "sub_activity_id": str(sub.id),
        "minutes_spent": 60, "description": "w", "tags_count": n,
    }
    res = client.post(
        REPORTS,
        json={"report_date": TODAY, "day_status": "work_at_office",
              "tasks": [task(400), task(700)]},
        headers=scoped["emp_a"],
    )
    assert res.status_code == 422, res.text


# ---------- editing ----------
def test_editing_a_report_does_not_count_its_own_previous_numbers(client, scoped):
    created = _report(client, scoped["emp_a"], scoped["project"], scoped["tags_sub"], 600)
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]

    # 600 -> 900. Naively this reads as 600 + 900 = 1500 and would be refused.
    res = client.patch(
        f"{REPORTS}/{report_id}",
        json={"tasks": [{
            "project_id": str(scoped["project"].id),
            "sub_activity_id": str(scoped["tags_sub"].id),
            "minutes_spent": 60, "description": "w", "tags_count": 900,
        }]},
        headers=scoped["emp_a"],
    )
    assert res.status_code == 200, res.text


def test_an_edit_is_still_capped_against_other_reports(client, scoped):
    created = _report(client, scoped["emp_a"], scoped["project"], scoped["tags_sub"], 300)
    report_id = created.json()["id"]
    _report(
        client, scoped["emp_b"], scoped["project"], scoped["tags_sub"], 600,
        day=YESTERDAY,
    )
    # B holds 600, so A may raise to at most 400.
    res = client.patch(
        f"{REPORTS}/{report_id}",
        json={"tasks": [{
            "project_id": str(scoped["project"].id),
            "sub_activity_id": str(scoped["tags_sub"].id),
            "minutes_spent": 60, "description": "w", "tags_count": 401,
        }]},
        headers=scoped["emp_a"],
    )
    assert res.status_code == 422, res.text


# ---------- the service helpers ----------
def test_remaining_falls_to_zero_and_never_below(db, scoped):
    p, sub = scoped["project"], scoped["tags_sub"]
    assert tag_progress.remaining_tags(db, p, sub) == 1000
    p.estimated_tag_count = 100
    db.add(p)
    db.commit()
    # An estimate reduced below what is already reported reads as 0, not negative.
    assert tag_progress.remaining_tags(db, p, sub) >= 0


def test_uncapped_situations_report_none(db, scoped):
    p, tags_sub, docs_sub = scoped["project"], scoped["tags_sub"], scoped["docs_sub"]
    assert tag_progress.remaining_tags(db, p, docs_sub) is None
    p.scope_type = "NONE"
    assert tag_progress.remaining_tags(db, p, tags_sub) is None


def test_summary_lists_each_activity_against_the_same_capacity(client, db, scoped):
    _report(client, scoped["emp_a"], scoped["project"], scoped["tags_sub"], 400)
    _report(
        client, scoped["emp_b"], scoped["project"], scoped["other_tags_sub"], 700,
        day=YESTERDAY,
    )
    rows = tag_progress.project_tag_progress(db, scoped["project"])
    by_name = {r["sub_activity_name"]: r for r in rows}
    assert by_name["FMTL-TAG DESCRIPTION"]["reported_tags"] == 400
    assert by_name["FMTL-TAG DESCRIPTION"]["remaining_tags"] == 600
    assert by_name["MTL-ASSET PHOTO MERGING"]["reported_tags"] == 700
    assert by_name["MTL-ASSET PHOTO MERGING"]["remaining_tags"] == 300
    # Same capacity on every row â€” not shares of a pool.
    assert {r["estimated_tag_count"] for r in rows} == {1000}
    # A docs activity never appears.
    assert "DOC-COLLECTION" not in by_name


def test_summary_is_empty_for_a_normal_project(db, scoped):
    p = scoped["project"]
    p.scope_type = "NONE"
    assert tag_progress.project_tag_progress(db, p) == []


