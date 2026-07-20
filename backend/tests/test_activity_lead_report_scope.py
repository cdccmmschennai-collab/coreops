"""Activity-Lead scoped report visibility.

An Activity Lead (project_activity_members.role = 'lead') may see another
employee's NON-DRAFT report only when it carries a task row on an exact
(project, activity) pair they Lead — and then only those rows, never the rest
of a mixed report. Own reports stay fully visible; Head/PM behavior is
unchanged; Leads gain no review/grant-edit authority. Backed by
authz.led_activity_pairs (deliberately separate from reviewable_project_ids,
which stays Head-only).
"""
import io
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.core import authz
from app.modules.activity_master import service as am_svc
from app.modules.activity_master.schemas import ActivityCreate, SubActivityCreate
from app.modules.projects import service as proj_svc
from app.modules.projects.models import ProjectStatus
from app.modules.projects.schemas import ActivityMemberCreate
from app.modules.users.models import UserRole
from app.modules.work_reports import service as wr_svc
from app.modules.work_reports.schemas import WorkReportCreate, WorkReportTaskIn
from app.shared.errors import AppError

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


def _activity_with_sub(db, code):
    act = am_svc.create_activity(db, ActivityCreate(code=code, name=code))
    sub = am_svc.create_sub_activity(
        db, act.id, SubActivityCreate(code=f"{code}-S", name=f"{code} Sub")
    )
    return act, sub


def _list(db, actor, **kw):
    params = dict(employee_id=None, project_id=None, status=None,
                  date_from=None, date_to=None, limit=50, offset=0)
    params.update(kw)
    return wr_svc.list_work_reports(db, actor, **params)


@pytest.fixture()
def scenario(db, make_user, make_employee, make_project, make_project_member):
    """Project P with activities FMTL (led by lead_u) and MTL (unled).
    The author files ONE mixed submitted report with a row on each."""
    pm_u = make_user("pm@x.com", role=UserRole.project_manager)
    project = make_project(code="LP-1", status=ProjectStatus.active)
    fmtl, fmtl_sub = _activity_with_sub(db, "FMTL")
    mtl, mtl_sub = _activity_with_sub(db, "MTL")

    lead_u = make_user("lead@x.com", role=UserRole.employee)
    lead_e = make_employee(employee_code="LD-1", user_id=lead_u.id)
    proj_svc.assign_activity_member(
        db, pm_u, project.id, fmtl.id,
        ActivityMemberCreate(employee_id=lead_e.id, role="lead"),
    )

    author_u = make_user("author@x.com", role=UserRole.employee)
    author_e = make_employee(employee_code="AU-1", user_id=author_u.id)
    make_project_member(project_id=project.id, employee_id=author_e.id)

    report = wr_svc.create_work_report(db, author_u, WorkReportCreate(
        report_date=TODAY,
        tasks=[
            WorkReportTaskIn(project_id=project.id, description="led work",
                             minutes_spent=60, sub_activity_id=fmtl_sub.id),
            WorkReportTaskIn(project_id=project.id, description="other work",
                             minutes_spent=30, sub_activity_id=mtl_sub.id),
        ],
    ))
    wr_svc.submit_work_report(db, author_u, report.id)
    return SimpleNamespace(
        pm_u=pm_u, project=project, fmtl=fmtl, fmtl_sub=fmtl_sub,
        mtl=mtl, mtl_sub=mtl_sub, lead_u=lead_u, lead_e=lead_e,
        author_u=author_u, author_e=author_e, report=report,
    )


# ---- core visibility -------------------------------------------------------
def test_lead_sees_foreign_led_row_only(db, scenario):
    s = scenario
    rows, total = _list(db, s.lead_u)
    assert total == 1
    r = rows[0]
    assert r.id == s.report.id
    # Mixed report: only the led activity's row, and the partial-view flag set.
    assert [t.sub_activity_id for t in r.tasks] == [s.fmtl_sub.id]
    assert r.scoped_to_led_activities is True
    assert r.can_review is False


def test_detail_access_trims_unrelated_rows(db, scenario):
    s = scenario
    out = wr_svc.get_work_report(db, s.lead_u, s.report.id)
    assert len(out.tasks) == 1
    assert out.tasks[0].sub_activity_id == s.fmtl_sub.id
    assert out.scoped_to_led_activities is True


def test_lead_cannot_see_foreign_draft(db, scenario):
    s = scenario
    draft = wr_svc.create_work_report(db, s.author_u, WorkReportCreate(
        report_date=YESTERDAY,
        tasks=[WorkReportTaskIn(project_id=s.project.id, description="d",
                                minutes_spent=15, sub_activity_id=s.fmtl_sub.id)],
    ))
    _rows, total = _list(db, s.lead_u)
    assert total == 1  # only the submitted report; the draft stays private
    with pytest.raises(AppError) as ei:
        wr_svc.get_work_report(db, s.lead_u, draft.id)
    assert ei.value.status_code == 403


def test_same_activity_in_unled_project_hidden(
    db, scenario, make_project, make_project_member
):
    s = scenario
    other = make_project(code="LP-2", status=ProjectStatus.active)
    make_project_member(project_id=other.id, employee_id=s.author_e.id)
    foreign = wr_svc.create_work_report(db, s.author_u, WorkReportCreate(
        report_date=YESTERDAY,
        tasks=[WorkReportTaskIn(project_id=other.id, description="same activity",
                                minutes_spent=60, sub_activity_id=s.fmtl_sub.id)],
    ))
    wr_svc.submit_work_report(db, s.author_u, foreign.id)

    rows, total = _list(db, s.lead_u)
    assert total == 1 and rows[0].id == s.report.id
    with pytest.raises(AppError) as ei:
        wr_svc.get_work_report(db, s.lead_u, foreign.id)
    assert ei.value.status_code == 403
    # The pair set itself is project-exact.
    assert authz.led_activity_pairs(db, s.lead_u) == {(s.project.id, s.fmtl.id)}


def test_filters_cannot_bypass_scope(
    db, scenario, make_project, make_project_member
):
    s = scenario
    other = make_project(code="LP-3", status=ProjectStatus.active)
    make_project_member(project_id=other.id, employee_id=s.author_e.id)
    foreign = wr_svc.create_work_report(db, s.author_u, WorkReportCreate(
        report_date=YESTERDAY,
        tasks=[WorkReportTaskIn(project_id=other.id, description="hidden",
                                minutes_spent=60, sub_activity_id=s.fmtl_sub.id)],
    ))
    wr_svc.submit_work_report(db, s.author_u, foreign.id)

    # Project filter cannot reach the unled project's report.
    _rows, total = _list(db, s.lead_u, project_id=other.id)
    assert total == 0
    # Employee filter still only yields the in-scope report.
    rows, total = _list(db, s.lead_u, employee_id=s.author_e.id)
    assert total == 1 and rows[0].id == s.report.id
    # Export rows: unled project / activity / sub-activity filters yield nothing.
    assert wr_svc.build_activity_rows(db, s.lead_u, project_id=other.id) == []
    assert wr_svc.build_activity_rows(db, s.lead_u, activity_id=s.mtl.id) == []
    assert wr_svc.build_activity_rows(db, s.lead_u, sub_activity_id=s.mtl_sub.id) == []


# ---- no review authority ---------------------------------------------------
def test_lead_cannot_grant_edit_or_review(db, scenario):
    s = scenario
    with pytest.raises(AppError) as ei:
        wr_svc.grant_edit_work_report(db, s.lead_u, s.report.id)
    assert ei.value.status_code == 403
    out = wr_svc.get_work_report(db, s.lead_u, s.report.id)
    assert out.can_review is False
    assert out.can_self_edit is False


# ---- own reports / other roles unchanged -----------------------------------
def test_lead_own_report_fully_visible(db, scenario):
    s = scenario
    own = wr_svc.create_work_report(db, s.lead_u, WorkReportCreate(
        report_date=TODAY,
        tasks=[
            WorkReportTaskIn(project_id=s.project.id, description="own led",
                             minutes_spent=30, sub_activity_id=s.fmtl_sub.id),
            WorkReportTaskIn(project_id=s.project.id, description="own unled",
                             minutes_spent=30, sub_activity_id=s.mtl_sub.id),
        ],
    ))
    out = wr_svc.get_work_report(db, s.lead_u, own.id)
    assert len(out.tasks) == 2
    assert out.scoped_to_led_activities is False


def test_pm_and_head_unchanged(db, scenario, make_user, make_employee):
    s = scenario
    # PM: full mixed report, no trimming.
    rows, total = _list(db, s.pm_u)
    assert total == 1
    assert len(rows[0].tasks) == 2
    assert rows[0].scoped_to_led_activities is False

    # Head of the project: full mixed report, review authority intact.
    head_u = make_user("head@x.com", role=UserRole.employee)
    head_e = make_employee(employee_code="HD-1", user_id=head_u.id)
    proj_svc.set_project_head(db, s.pm_u, s.project.id, head_e.id)
    out = wr_svc.get_work_report(db, head_u, s.report.id)
    assert len(out.tasks) == 2
    assert out.scoped_to_led_activities is False
    assert out.can_review is True


def test_contributor_remains_own_only(db, scenario, make_user, make_employee,
                                      make_project_member):
    s = scenario
    con_u = make_user("con@x.com", role=UserRole.employee)
    con_e = make_employee(employee_code="CN-1", user_id=con_u.id)
    make_project_member(project_id=s.project.id, employee_id=con_e.id)
    _rows, total = _list(db, con_u)
    assert total == 0
    with pytest.raises(AppError) as ei:
        wr_svc.get_work_report(db, con_u, s.report.id)
    assert ei.value.status_code == 403


# ---- export parity ---------------------------------------------------------
def test_export_rows_scoped_to_led_activities(db, scenario):
    s = scenario
    rows = wr_svc.build_activity_rows(db, s.lead_u)
    assert [r["sub_activity_type"] for r in rows] == ["FMTL Sub"]
    groups = wr_svc.build_activity_groups(db, s.lead_u)
    acts = [a for g in groups["rows"] for a in g["activities"]]
    assert [a["sub_activity_type"] for a in acts] == ["FMTL Sub"]


def test_excel_and_json_preview_match(client, login, scenario):
    s = scenario
    hdr = login("lead@x.com")
    res = client.get("/api/v1/reports-export/activity-rows", headers=hdr)
    assert res.status_code == 200, res.text
    json_subs = [
        a["sub_activity_type"] for row in res.json()["rows"]
        for a in row["activities"]
    ]
    assert json_subs == ["FMTL Sub"]

    res_x = client.get("/api/v1/reports-export/activity-rows.xlsx", headers=hdr)
    assert res_x.status_code == 200
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(res_x.content))
    cells = {
        str(c.value) for ws in wb.worksheets for row in ws.iter_rows()
        for c in row if c.value is not None
    }
    assert "FMTL Sub" in cells
    assert "MTL Sub" not in cells


# ---- lifecycle / mixed roles -----------------------------------------------
def test_removing_lead_assignment_removes_access(db, scenario):
    s = scenario
    proj_svc.remove_activity_member(db, s.pm_u, s.project.id, s.fmtl.id, s.lead_e.id)
    _rows, total = _list(db, s.lead_u)
    assert total == 0
    with pytest.raises(AppError) as ei:
        wr_svc.get_work_report(db, s.lead_u, s.report.id)
    assert ei.value.status_code == 403


def test_head_plus_lead_union(db, scenario, make_user, make_employee,
                              make_project, make_project_member):
    """lead_u Heads project A and Leads FMTL in project P: full visibility on
    A's reports, led-rows-only on P's, nothing elsewhere."""
    s = scenario
    proj_a = make_project(code="LP-A", status=ProjectStatus.active)
    author2_u = make_user("author2@x.com", role=UserRole.employee)
    author2_e = make_employee(employee_code="AU-2", user_id=author2_u.id)
    make_project_member(project_id=proj_a.id, employee_id=author2_e.id)
    proj_svc.set_project_head(db, s.pm_u, proj_a.id, s.lead_e.id)

    rep_a = wr_svc.create_work_report(db, author2_u, WorkReportCreate(
        report_date=TODAY,
        tasks=[WorkReportTaskIn(project_id=proj_a.id, description="head-scope",
                                minutes_spent=45, sub_activity_id=s.mtl_sub.id)],
    ))
    wr_svc.submit_work_report(db, author2_u, rep_a.id)

    rows, total = _list(db, s.lead_u)
    assert total == 2
    by_id = {r.id: r for r in rows}
    # Project A (headed): full report, even though MTL is not a led activity.
    assert len(by_id[rep_a.id].tasks) == 1
    assert by_id[rep_a.id].scoped_to_led_activities is False
    assert by_id[rep_a.id].can_review is True
    # Project P (led only): still trimmed to the led row.
    assert [t.sub_activity_id for t in by_id[s.report.id].tasks] == [s.fmtl_sub.id]
    assert by_id[s.report.id].scoped_to_led_activities is True


# ---- scope endpoint --------------------------------------------------------
def test_report_scope_for_lead(db, client, login, scenario):
    s = scenario
    out = wr_svc.get_report_scope(db, s.lead_u)
    assert out["is_project_head"] is False
    assert out["is_activity_lead"] is True
    assert len(out["projects"]) == 1
    p = out["projects"][0]
    assert p["project_id"] == s.project.id
    assert p["access"] == "lead"
    assert [a["activity_id"] for a in p["activities"]] == [s.fmtl.id]
    member_ids = {m["employee_id"] for m in p["members"]}
    assert {s.author_e.id, s.lead_e.id} <= member_ids

    res = client.get("/api/v1/work-reports/scope", headers=login("lead@x.com"))
    assert res.status_code == 200, res.text
    assert res.json()["is_activity_lead"] is True


def test_report_scope_empty_for_pm_and_contributor(db, scenario, make_user,
                                                   make_employee):
    s = scenario
    assert wr_svc.get_report_scope(db, s.pm_u)["projects"] == []
    con_u = make_user("con2@x.com", role=UserRole.employee)
    make_employee(employee_code="CN-2", user_id=con_u.id)
    out = wr_svc.get_report_scope(db, con_u)
    assert out == {"is_project_head": False, "is_activity_lead": False, "projects": []}
