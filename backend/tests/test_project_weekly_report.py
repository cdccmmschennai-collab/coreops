"""Project Weekly Report (Phase 7) — the Head's Fri-Thu operational report.

What the report is:

  Every activity line reported on ONE project during ONE Friday-Thursday cycle,
  one row per employee + date + work period + activity, for the assigned Head.

The two things these tests exist to pin down:

  1. It is NOT the tag-scope view. Docs work, task-mode work and activities with
     no benchmark at all appear alongside tag work, on tag-scoped projects and
     ordinary ones alike.
  2. Access is the assigned Head of THIS project and nobody else — not a member,
     not a PM, not the Head of a different project — and that is enforced by the
     API, not by hiding a tab.

Excel parity lives in test_project_weekly_report_export.py.
"""
from datetime import date, timedelta

import pytest

from app.modules.activity_master.models import ActivityMaster
from app.modules.projects import weekly_report
from app.modules.projects.models import ProjectMember, ProjectStatus
from app.modules.users.models import UserRole

BASE = "/api/v1/projects"
REPORTS = "/api/v1/work-reports"

# Report dates are validated against "not in the future", so every literal here
# is derived from today rather than hard-coded.
TODAY = date.today()
LAST_CYCLE = TODAY - timedelta(days=7)     # exactly one Fri-Thu cycle back
TWO_CYCLES_AGO = TODAY - timedelta(days=14)


@pytest.fixture()
def day_parts_on():
    """Split-Day reporting (migration 0060) is feature-flagged; the suite pins
    it off by default."""
    from app.core.config import settings

    prev = settings.REPORT_DAY_PARTS_ENABLED
    settings.REPORT_DAY_PARTS_ENABLED = True
    try:
        yield
    finally:
        settings.REPORT_DAY_PARTS_ENABLED = prev


@pytest.fixture()
def wr(db, make_project, make_user, make_employee, make_project_member, login, client):
    """Two projects, each with its own Head, plus the four kinds of activity the
    report has to represent.

    The reported project is deliberately scope_type NONE (no tag scope at all) —
    the Weekly Report must work on an ordinary project, not only a tag-scoped
    one.
    """
    project = make_project(code="WR-ALPHA", name="Alpha Works", status=ProjectStatus.active)
    other = make_project(code="WR-BETA", name="Beta Works", status=ProjectStatus.active)

    fmtl = ActivityMaster(name="FMTL", level="activity")
    docs_act = ActivityMaster(name="DOCUMENTATION", level="activity")
    tool = ActivityMaster(name="TOOL SUPPORT", level="activity")
    meeting = ActivityMaster(name="PROJECT MEETING", level="activity")
    db.add_all([fmtl, docs_act, tool, meeting])
    db.commit()

    def sub(name, parent, **kw):
        row = ActivityMaster(name=name, level="sub_activity", parent_id=parent.id, **kw)
        db.add(row)
        return row

    tags_sub = sub(
        "FMTL-TAG DESCRIPTION FROM P&ID", fmtl,
        benchmark_type="NUMERIC_DAILY", benchmark_value=300, relevant_count_field="tags",
    )
    docs_sub = sub(
        "DOC COLLECTION", docs_act,
        benchmark_type="NUMERIC_DAILY", benchmark_value=20, relevant_count_field="docs",
    )
    task_sub = sub(
        "TOOL SUPPORT-ENVIRONMENT SETUP", tool,
        benchmark_type="TASK_STATUS_ONLY", benchmark_period_days=2,
    )
    meeting_sub = sub("PROJECT MEETING-MTL", meeting)   # no benchmark at all
    db.commit()

    def person(email, code, first, last, *, projects):
        user = make_user(email, "password123", UserRole.employee)
        emp = make_employee(
            employee_code=code, first_name=first, last_name=last, user_id=user.id
        )
        for p in projects:
            db.add(ProjectMember(project_id=p.id, employee_id=emp.id))
        db.commit()
        return {"emp": emp, "header": login(email)}

    head = person("wr.head@x.com", "WR-H", "Hari", "Krishnan", projects=[project])
    other_head = person("wr.other@x.com", "WR-OH", "Omar", "Basha", projects=[other])
    alice = person("wr.alice@x.com", "WR-A", "Alice", "Anand", projects=[project, other])
    bob = person("wr.bob@x.com", "WR-B", "Bala", "Murugan", projects=[project])

    project.head_employee_id = head["emp"].id
    other.head_employee_id = other_head["emp"].id
    db.add_all([project, other])
    db.commit()

    make_user("wr.pm@x.com", "password123", UserRole.project_manager)

    return {
        "project": project,
        "other": other,
        "tags_sub": tags_sub,
        "docs_sub": docs_sub,
        "task_sub": task_sub,
        "meeting_sub": meeting_sub,
        "head": head["header"],
        "other_head": other_head["header"],
        "alice": alice["header"],
        "bob": bob["header"],
        "pm": login("wr.pm@x.com"),
    }


# ---------- helpers ---------------------------------------------------------
def _task(project, sub, **over):
    task = {
        "project_id": str(project.id),
        "sub_activity_id": str(sub.id),
        "minutes_spent": 240,
        "description": "worked on it",
    }
    task.update(over)
    return task


def _file(client, headers, day, tasks, **body):
    """Create a report and SUBMIT it — the report is only real work once filed."""
    payload = {
        "report_date": day.isoformat(),
        "day_status": "work_at_office",
        "tasks": tasks,
    }
    payload.update(body)
    res = client.post(REPORTS, json=payload, headers=headers)
    assert res.status_code == 201, res.text
    report_id = res.json()["id"]
    res = client.post(f"{REPORTS}/{report_id}/submit", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _draft(client, headers, day, tasks):
    res = client.post(
        REPORTS,
        json={"report_date": day.isoformat(), "day_status": "work_at_office", "tasks": tasks},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


def _report(client, headers, project, cycle="current", expect=200):
    res = client.get(f"{BASE}/{project.id}/weekly-report?cycle={cycle}", headers=headers)
    assert res.status_code == expect, res.text
    return res.json()


def _by_sub(payload):
    return {r["sub_activity_name"]: r for r in payload["rows"]}


# ---------- permissions -----------------------------------------------------
def test_assigned_head_reads_both_cycles(client, wr):
    _file(client, wr["alice"], TODAY, [_task(wr["project"], wr["tags_sub"], tags_count=250)])
    _file(client, wr["alice"], LAST_CYCLE,
          [_task(wr["project"], wr["tags_sub"], tags_count=100)])

    current = _report(client, wr["head"], wr["project"], "current")
    previous = _report(client, wr["head"], wr["project"], "previous")
    assert current["row_count"] == 1
    assert previous["row_count"] == 1
    assert current["rows"][0]["tags"] == 250
    assert previous["rows"][0]["tags"] == 100


def test_head_of_another_project_is_denied(client, wr):
    """Head authority is per-project. Heading Beta grants nothing on Alpha."""
    assert _report(client, wr["other_head"], wr["project"], expect=403)
    res = client.get(f"{BASE}/{wr['project'].id}/weekly-report.xlsx", headers=wr["other_head"])
    assert res.status_code == 403, res.text


def test_an_ordinary_project_member_is_denied(client, wr):
    """Alice may open the project, its Tag Scope and its Summary — the Weekly
    Report is still not hers."""
    assert client.get(f"{BASE}/{wr['project'].id}", headers=wr["alice"]).status_code == 200
    assert client.get(f"{BASE}/{wr['project'].id}/summary", headers=wr["alice"]).status_code == 200
    assert _report(client, wr["alice"], wr["project"], expect=403)


def test_a_project_manager_is_denied(client, wr):
    """The current requirement is Head-only. A PM is not silently included."""
    assert _report(client, wr["pm"], wr["project"], expect=403)
    res = client.get(f"{BASE}/{wr['project'].id}/weekly-report.xlsx", headers=wr["pm"])
    assert res.status_code == 403, res.text


def test_the_export_repeats_the_authorization(client, wr):
    """A hand-typed export URL is not protected by a hidden button."""
    for headers in ("alice", "other_head", "pm"):
        res = client.get(
            f"{BASE}/{wr['project'].id}/weekly-report.xlsx?cycle=previous",
            headers=wr[headers],
        )
        assert res.status_code == 403, (headers, res.text)
    ok = client.get(f"{BASE}/{wr['project'].id}/weekly-report.xlsx", headers=wr["head"])
    assert ok.status_code == 200, ok.text


def test_a_missing_project_is_404(client, wr):
    import uuid as _uuid

    res = client.get(f"{BASE}/{_uuid.uuid4()}/weekly-report", headers=wr["head"])
    assert res.status_code == 404, res.text


def test_an_unsupported_cycle_is_rejected(client, wr):
    res = client.get(f"{BASE}/{wr['project'].id}/weekly-report?cycle=last-month",
                     headers=wr["head"])
    assert res.status_code == 422, res.text
    res = client.get(f"{BASE}/{wr['project'].id}/weekly-report?cycle=3", headers=wr["head"])
    assert res.status_code == 422, res.text


# ---------- the cycle -------------------------------------------------------
@pytest.mark.parametrize("reference,expected_start", [
    (date(2026, 8, 7), date(2026, 8, 7)),    # Friday — the cycle opens
    (date(2026, 8, 10), date(2026, 8, 7)),   # Monday inside it
    (date(2026, 8, 13), date(2026, 8, 7)),   # Thursday — the cycle closes
    (date(2026, 8, 14), date(2026, 8, 14)),  # next Friday — a new cycle
])
def test_current_cycle_is_friday_to_thursday(reference, expected_start):
    cycle, start, end = weekly_report.resolve_cycle("current", today=reference)
    assert (cycle, start, end) == ("current", expected_start, expected_start + timedelta(days=6))
    assert start.weekday() == 4   # Friday
    assert end.weekday() == 3     # Thursday


def test_previous_cycle_is_the_one_immediately_before():
    _, start, end = weekly_report.resolve_cycle("previous", today=date(2026, 8, 10))
    assert (start, end) == (date(2026, 7, 31), date(2026, 8, 6))
    _, cur_start, _ = weekly_report.resolve_cycle("current", today=date(2026, 8, 10))
    assert end + timedelta(days=1) == cur_start


def test_the_boundary_friday_belongs_to_the_new_cycle():
    """13-Aug (Thu) and 14-Aug (Fri) are in different cycles, one day apart."""
    _, thu_start, _ = weekly_report.resolve_cycle("current", today=date(2026, 8, 13))
    _, fri_start, _ = weekly_report.resolve_cycle("current", today=date(2026, 8, 14))
    assert thu_start == date(2026, 8, 7)
    assert fri_start == date(2026, 8, 14)


def test_the_resolved_range_is_echoed_back(client, wr):
    payload = _report(client, wr["head"], wr["project"], "current")
    start = date.fromisoformat(payload["period"]["start_date"])
    end = date.fromisoformat(payload["period"]["end_date"])
    assert payload["period"]["type"] == "current"
    assert start.weekday() == 4 and end.weekday() == 3
    assert (end - start).days == 6
    assert start <= TODAY <= end


def test_an_unsupported_cycle_raises_rather_than_defaulting():
    with pytest.raises(ValueError):
        weekly_report.resolve_cycle("next")


# ---------- what is in the window ------------------------------------------
def test_work_outside_the_selected_cycle_is_excluded(client, wr):
    _file(client, wr["alice"], TODAY, [_task(wr["project"], wr["tags_sub"], tags_count=10)])
    _file(client, wr["alice"], LAST_CYCLE, [_task(wr["project"], wr["tags_sub"], tags_count=20)])
    _file(client, wr["alice"], TWO_CYCLES_AGO,
          [_task(wr["project"], wr["tags_sub"], tags_count=30)])

    current = _report(client, wr["head"], wr["project"], "current")
    previous = _report(client, wr["head"], wr["project"], "previous")
    assert [r["tags"] for r in current["rows"]] == [10]
    assert [r["tags"] for r in previous["rows"]] == [20]
    # The 2-cycles-ago row is in neither.
    assert 30 not in [r["tags"] for r in current["rows"] + previous["rows"]]


def test_only_this_projects_work_appears(client, wr):
    """Alice works on both projects on the same day; Alpha's report shows only
    Alpha's line."""
    _file(client, wr["alice"], TODAY, [
        _task(wr["project"], wr["tags_sub"], tags_count=250),
        _task(wr["other"], wr["tags_sub"], tags_count=999),
    ])

    payload = _report(client, wr["head"], wr["project"])
    assert payload["row_count"] == 1
    assert payload["rows"][0]["tags"] == 250
    assert {r["project_code"] for r in payload["rows"]} == {"WR-ALPHA"}


def test_a_draft_report_never_appears(client, wr):
    """Drafts are private to their author until filed — the Head's formal weekly
    report is not the one place they leak."""
    _draft(client, wr["alice"], TODAY, [_task(wr["project"], wr["tags_sub"], tags_count=77)])

    payload = _report(client, wr["head"], wr["project"])
    assert payload["rows"] == []


def test_a_reopened_report_still_counts(client, wr):
    """'granted' (the Head reopened it for editing) is real recorded work and
    stays visible — otherwise granting an edit would erase the week."""
    filed = _file(client, wr["alice"], TODAY,
                  [_task(wr["project"], wr["tags_sub"], tags_count=250)])
    res = client.post(f"{REPORTS}/{filed['id']}/request-edit",
                      json={"note": "wrong count"}, headers=wr["alice"])
    assert res.status_code == 200, res.text
    res = client.post(f"{REPORTS}/{filed['id']}/grant-edit", headers=wr["head"])
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "granted"

    payload = _report(client, wr["head"], wr["project"])
    assert [r["tags"] for r in payload["rows"]] == [250]


def test_an_empty_week_is_an_empty_report_not_an_error(client, wr):
    payload = _report(client, wr["head"], wr["project"], "previous")
    assert payload["rows"] == []
    assert payload["row_count"] == 0
    assert payload["project_code"] == "WR-ALPHA"
    assert payload["period"]["type"] == "previous"


# ---------- the columns -----------------------------------------------------
def test_project_column_is_the_code_only(client, wr):
    """Never the project name, and never "name + code"."""
    _file(client, wr["alice"], TODAY, [_task(wr["project"], wr["tags_sub"], tags_count=250)])

    payload = _report(client, wr["head"], wr["project"])
    row = payload["rows"][0]
    assert row["project_code"] == "WR-ALPHA"
    assert "Alpha Works" not in str(row)
    assert payload["project_code"] == "WR-ALPHA"


def test_activity_and_sub_activity_are_separate_columns(client, wr):
    _file(client, wr["alice"], TODAY, [_task(wr["project"], wr["tags_sub"], tags_count=250)])

    row = _report(client, wr["head"], wr["project"])["rows"][0]
    assert row["activity_name"] == "FMTL"
    assert row["sub_activity_name"] == "FMTL-TAG DESCRIPTION FROM P&ID"


def test_employee_name_is_the_display_name(client, wr):
    _file(client, wr["alice"], TODAY, [_task(wr["project"], wr["tags_sub"], tags_count=250)])

    row = _report(client, wr["head"], wr["project"])["rows"][0]
    assert row["employee_name"] == "Alice Anand"
    assert "@" not in row["employee_name"]


def test_remarks_prefer_the_activity_lines_own_note(client, wr):
    _file(client, wr["alice"], TODAY, [
        _task(wr["project"], wr["tags_sub"], tags_count=250, description="FAHN MTL 250 TAGS"),
    ], remarks="day-level note", query_text="a question for the PM")

    row = _report(client, wr["head"], wr["project"])["rows"][0]
    assert row["remarks"] == "FAHN MTL 250 TAGS"
    # The more general day note is not appended to the more specific one.
    assert "day-level note" not in row["remarks"]


def test_a_full_day_row_falls_back_to_the_day_note(client, wr):
    """The report form does not collect a per-activity note today, so a column
    reading only work_report_tasks.description would be empty on every real
    row. A Full Day row therefore carries the report's own note - the same
    definition the benchmark export's REMARKS column already uses."""
    _file(client, wr["alice"], TODAY,
          [_task(wr["project"], wr["tags_sub"], tags_count=250, description="")],
          remarks="COMPLETED FAHN MTL FOR 250 TAGS")

    row = _report(client, wr["head"], wr["project"])["rows"][0]
    assert row["remarks"] == "COMPLETED FAHN MTL FOR 250 TAGS"


def test_the_query_field_is_never_merged_into_remarks(client, wr):
    """Query / Issues is a question for the PM, not a description of the work."""
    _file(client, wr["alice"], TODAY,
          [_task(wr["project"], wr["tags_sub"], tags_count=250, description="")],
          remarks="", query_text="which drawing revision applies?")

    row = _report(client, wr["head"], wr["project"])["rows"][0]
    assert row["remarks"] is None


def test_each_half_carries_its_own_note_not_the_days(client, wr, day_parts_on):
    """A half-day row never inherits the header note: attributing a remark about
    the morning to the afternoon's activity would be worse than a blank cell."""
    res = client.post(REPORTS, json={
        "report_date": TODAY.isoformat(),
        "report_mode": "split_day",
        "remarks": "whole-day note",
        "periods": [
            {"day_part": "first_half", "period_status": "work_at_office",
             "remarks": "morning: 140 tags",
             "tasks": [_task(wr["project"], wr["tags_sub"], tags_count=140,
                             minutes_spent=240, description="")]},
            {"day_part": "second_half", "period_status": "work_at_office",
             "tasks": [_task(wr["project"], wr["docs_sub"], docs_count=8,
                             minutes_spent=240, description="")]},
        ],
    }, headers=wr["alice"])
    assert res.status_code == 201, res.text
    client.post(f"{REPORTS}/{res.json()['id']}/submit", headers=wr["alice"])

    rows = _by_sub(_report(client, wr["head"], wr["project"]))
    assert rows["FMTL-TAG DESCRIPTION FROM P&ID"]["remarks"] == "morning: 140 tags"
    # The second half wrote no note of its own, and does not borrow the day's.
    assert rows["DOC COLLECTION"]["remarks"] is None


# ---------- every kind of activity -----------------------------------------
def test_a_numeric_tag_activity_carries_its_benchmark_and_count(client, wr):
    _file(client, wr["alice"], TODAY, [_task(wr["project"], wr["tags_sub"], tags_count=250)])

    row = _report(client, wr["head"], wr["project"])["rows"][0]
    assert row["benchmark"] == 300
    assert row["benchmark_label"] is None
    assert row["tags"] == 250
    # The units this row does not measure stay blank, not zero.
    assert (row["docs"], row["bom"], row["spares"], row["pages"], row["records"]) == (
        None, None, None, None, None
    )
    assert row["task_status"] is None


def test_a_document_activity_is_included(client, wr):
    """Doc-counted work is project work. Filtering the report to tag activities
    would drop it — that rule belongs to Tag Scope / Summary, not here."""
    _file(client, wr["alice"], TODAY, [_task(wr["project"], wr["docs_sub"], docs_count=15)])

    row = _report(client, wr["head"], wr["project"])["rows"][0]
    assert row["sub_activity_name"] == "DOC COLLECTION"
    assert row["docs"] == 15
    assert row["tags"] is None
    assert row["benchmark"] == 20


def test_a_task_based_activity_is_included_with_its_status(client, wr):
    _file(client, wr["alice"], TODAY, [_task(wr["project"], wr["task_sub"])])

    row = _report(client, wr["head"], wr["project"])["rows"][0]
    assert row["sub_activity_name"] == "TOOL SUPPORT-ENVIRONMENT SETUP"
    assert row["task_status"] == "IN_PROGRESS"
    assert row["task_status_label"] == "In progress"
    # A completion-only task has no numeric target and no meaningful counts.
    assert row["benchmark"] is None
    assert row["benchmark_label"] == "Lump Sum"
    assert all(row[u] is None for u in ("tags", "docs", "bom", "spares", "pages", "records"))


def test_a_completed_task_reports_completion(client, wr):
    _file(client, wr["alice"], TODAY,
          [_task(wr["project"], wr["task_sub"], is_completed=True)])

    row = _report(client, wr["head"], wr["project"])["rows"][0]
    assert row["task_status"] in ("COMPLETED_ON_TIME", "COMPLETED_LATE")
    assert row["task_status_label"].startswith("Completed")


def test_a_non_benchmark_activity_is_included(client, wr):
    """PROJECT MEETING has no benchmark configuration at all. The row still
    appears; only its Benchmark cell is empty."""
    _file(client, wr["alice"], TODAY, [_task(wr["project"], wr["meeting_sub"])])

    row = _report(client, wr["head"], wr["project"])["rows"][0]
    assert row["activity_name"] == "PROJECT MEETING"
    assert row["benchmark"] is None
    assert row["benchmark_label"] is None
    assert row["task_status"] is None


def test_all_four_kinds_appear_together(client, wr):
    """One day, four activities of four different shapes — four rows, none
    dropped for lacking a tag count or a benchmark."""
    _file(client, wr["alice"], TODAY, [
        _task(wr["project"], wr["tags_sub"], tags_count=250),
        _task(wr["project"], wr["docs_sub"], docs_count=15),
        _task(wr["project"], wr["task_sub"]),
        _task(wr["project"], wr["meeting_sub"]),
    ])

    rows = _by_sub(_report(client, wr["head"], wr["project"]))
    assert len(rows) == 4
    assert rows["FMTL-TAG DESCRIPTION FROM P&ID"]["tags"] == 250
    assert rows["DOC COLLECTION"]["docs"] == 15
    assert rows["TOOL SUPPORT-ENVIRONMENT SETUP"]["task_status"] == "IN_PROGRESS"
    assert rows["PROJECT MEETING-MTL"]["benchmark"] is None


def test_a_project_with_no_tag_scope_still_reports(client, db, wr):
    """The tab does not depend on the project being tag-scoped."""
    assert wr["project"].scope_type == "NONE"
    _file(client, wr["alice"], TODAY, [_task(wr["project"], wr["tags_sub"], tags_count=250)])

    assert _report(client, wr["head"], wr["project"])["row_count"] == 1


# ---------- granularity, split days and ordering ---------------------------
def test_two_activities_on_one_day_stay_two_rows(client, wr):
    _file(client, wr["alice"], TODAY, [
        _task(wr["project"], wr["tags_sub"], tags_count=100),
        _task(wr["project"], wr["docs_sub"], docs_count=25),
    ])

    payload = _report(client, wr["head"], wr["project"])
    assert payload["row_count"] == 2
    assert {r["sub_activity_name"] for r in payload["rows"]} == {
        "FMTL-TAG DESCRIPTION FROM P&ID", "DOC COLLECTION"
    }


def test_a_full_day_report_reads_full_day(client, wr):
    _file(client, wr["alice"], TODAY, [_task(wr["project"], wr["tags_sub"], tags_count=250)])

    row = _report(client, wr["head"], wr["project"])["rows"][0]
    assert row["work_period"] == "full_day"
    assert row["work_period_label"] == "Full Day"


def test_a_split_day_lands_in_two_projects_correctly(client, wr, day_parts_on):
    """Alice: first half on Alpha, second half on Beta.

    Alpha's report must show ONE first-half row, Beta's ONE second-half row, and
    neither may look like a full day.
    """
    res = client.post(REPORTS, json={
        "report_date": TODAY.isoformat(),
        "report_mode": "split_day",
        "periods": [
            {
                "day_part": "first_half",
                "period_status": "work_at_office",
                "remarks": "alpha morning",
                "tasks": [_task(wr["project"], wr["tags_sub"], tags_count=120,
                                minutes_spent=240, description="alpha tags")],
            },
            {
                "day_part": "second_half",
                "period_status": "work_at_office",
                "remarks": "beta afternoon",
                "tasks": [_task(wr["other"], wr["docs_sub"], docs_count=9,
                                minutes_spent=240, description="beta docs")],
            },
        ],
    }, headers=wr["alice"])
    assert res.status_code == 201, res.text
    assert client.post(f"{REPORTS}/{res.json()['id']}/submit",
                       headers=wr["alice"]).status_code == 200

    alpha = _report(client, wr["head"], wr["project"])
    assert alpha["row_count"] == 1
    assert alpha["rows"][0]["work_period"] == "first_half"
    assert alpha["rows"][0]["work_period_label"] == "First Half"
    assert alpha["rows"][0]["project_code"] == "WR-ALPHA"
    assert alpha["rows"][0]["tags"] == 120

    beta = _report(client, wr["other_head"], wr["other"])
    assert beta["row_count"] == 1
    assert beta["rows"][0]["work_period"] == "second_half"
    assert beta["rows"][0]["project_code"] == "WR-BETA"

    # Neither project reports the day as a full day.
    assert "full_day" not in {alpha["rows"][0]["work_period"], beta["rows"][0]["work_period"]}


def test_half_day_benchmark_is_the_effective_target(client, wr, day_parts_on):
    """The benchmark shown is the frozen effective target — a half day of a
    300/day activity was measured against 150, and that is what the Head sees."""
    res = client.post(REPORTS, json={
        "report_date": TODAY.isoformat(),
        "report_mode": "split_day",
        "periods": [
            {"day_part": "first_half", "period_status": "work_at_office",
             "tasks": [_task(wr["project"], wr["tags_sub"], tags_count=140, minutes_spent=240)]},
            {"day_part": "second_half", "period_status": "work_at_office",
             "tasks": [_task(wr["project"], wr["docs_sub"], docs_count=8, minutes_spent=240)]},
        ],
    }, headers=wr["alice"])
    assert res.status_code == 201, res.text
    client.post(f"{REPORTS}/{res.json()['id']}/submit", headers=wr["alice"])

    rows = _by_sub(_report(client, wr["head"], wr["project"]))
    assert rows["FMTL-TAG DESCRIPTION FROM P&ID"]["benchmark"] == 150
    assert rows["DOC COLLECTION"]["benchmark"] == 10


def test_rows_are_ordered_by_date_then_period_then_employee(client, wr, day_parts_on):
    _file(client, wr["bob"], LAST_CYCLE, [_task(wr["project"], wr["tags_sub"], tags_count=1)])
    _file(client, wr["alice"], LAST_CYCLE, [_task(wr["project"], wr["tags_sub"], tags_count=2)])
    _file(client, wr["bob"], LAST_CYCLE + timedelta(days=1),
          [_task(wr["project"], wr["tags_sub"], tags_count=3)])

    payload = _report(client, wr["head"], wr["project"], "previous")
    got = [(r["report_date"], r["employee_name"]) for r in payload["rows"]]
    assert got == [
        (LAST_CYCLE.isoformat(), "Alice Anand"),        # same date -> name asc
        (LAST_CYCLE.isoformat(), "Bala Murugan"),
        ((LAST_CYCLE + timedelta(days=1)).isoformat(), "Bala Murugan"),
    ]


def test_full_day_sorts_before_first_and_second_half(client, wr, day_parts_on):
    """Alice files a split day, Bob a full day, on the same date. Work Period
    orders Full Day, First Half, Second Half — never DB insertion order."""
    day = LAST_CYCLE
    res = client.post(REPORTS, json={
        "report_date": day.isoformat(),
        "report_mode": "split_day",
        "periods": [
            {"day_part": "first_half", "period_status": "work_at_office",
             "tasks": [_task(wr["project"], wr["tags_sub"], tags_count=5, minutes_spent=240)]},
            {"day_part": "second_half", "period_status": "work_at_office",
             "tasks": [_task(wr["project"], wr["docs_sub"], docs_count=2, minutes_spent=240)]},
        ],
    }, headers=wr["alice"])
    assert res.status_code == 201, res.text
    client.post(f"{REPORTS}/{res.json()['id']}/submit", headers=wr["alice"])
    _file(client, wr["bob"], day, [_task(wr["project"], wr["tags_sub"], tags_count=7)])

    periods = [r["work_period"] for r in
               _report(client, wr["head"], wr["project"], "previous")["rows"]]
    assert periods == ["full_day", "first_half", "second_half"]


def test_the_same_request_twice_returns_the_same_order(client, wr):
    _file(client, wr["alice"], TODAY, [
        _task(wr["project"], wr["tags_sub"], tags_count=100),
        _task(wr["project"], wr["docs_sub"], docs_count=25),
        _task(wr["project"], wr["meeting_sub"]),
    ])

    first = _report(client, wr["head"], wr["project"])["rows"]
    second = _report(client, wr["head"], wr["project"])["rows"]
    assert first == second
