"""Production Status - Phase 4 (PM cumulative report + Excel export).

Focused suite for the report only. Nothing here touches the Phase 1-3 recording
workflow; those rules are covered in test_production_status.py and are unchanged.

Covers, in order:

  1. PM can read the report               test_project_manager_can_read_report
  2. Head / Lead / employee get 403       test_non_pm_roles_are_rejected
  3. same 403 over HTTP                   test_report_endpoints_are_pm_only_over_http
  4. every project appears                test_report_spans_every_project
  5. every activity in a project appears  test_report_includes_every_activity
  6. REV-0 and REV-1 both survive         test_both_revisions_appear
  7. only the latest row per combination  test_only_latest_row_per_combination
  8. counts stay four independent values  test_counts_are_four_independent_values
  9. BY is the person, not the role       test_by_is_the_actual_person_name
 10. null completed_on stays null         test_null_completed_on_stays_null
 11. remarks are never truncated          test_full_remarks_are_preserved
 12. zero counts stay numeric zero        test_zero_counts_stay_numeric_zero
 13. PROJECT / PLANT convention           test_project_plant_uses_project_information
 14. empty report                         test_empty_report
 15. workbook == the preview dataset      test_workbook_matches_the_report_dataset
 16. workbook columns + formatting        test_workbook_columns_and_formatting
 17. the download is a valid .xlsx        test_download_produces_a_valid_xlsx
 18. the report reads no history          test_report_never_returns_history_rows

Run:  docker exec wms-backend-1 pytest tests/test_production_status_report.py -q
"""
from datetime import date
from io import BytesIO

import openpyxl
import pytest

from app.modules.activity_master import service as am_svc
from app.modules.activity_master.schemas import ActivityCreate
from app.modules.plants.models import MaintenancePlant, PlanningPlant
from app.modules.production_status import service as ps_svc
from app.modules.production_status.schemas import ProductionStatusCreate
from app.modules.projects import service as proj_svc
from app.modules.projects.models import ProjectStatus
from app.modules.projects.schemas import ActivityMemberCreate
from app.modules.reports_export import export
from app.modules.users.models import UserRole
from app.shared.errors import AppError

REPORT_URL = "/api/v1/production-status/report"
XLSX_URL = "/api/v1/production-status/report.xlsx"


# --- helpers ---------------------------------------------------------------

def _activity(db, code):
    return am_svc.create_activity(db, ActivityCreate(code=code, name=code))


def _payload(activity_id, **over):
    body = dict(
        revision="REV-0",
        activity_id=activity_id,
        status="in_progress",
        tag_count=0,
        doc_count=0,
        spares_count=0,
        crs_count=0,
    )
    body.update(over)
    return ProductionStatusCreate(**body)


def _rows(report):
    return report["rows"]


def _find(report, *, project_code, revision, activity):
    """The one row for a project + revision + activity, or None."""
    for row in _rows(report):
        if (
            row.project_code == project_code
            and row.revision == revision
            and row.activity == activity
        ):
            return row
    return None


@pytest.fixture()
def scene(db, make_user, make_employee, make_project):
    """Two projects, so "cumulative" is actually exercised.

      pm        project_manager - the only role the report serves
      project_a code GC-A, Head = head_u, activities TAG ESTIMATION + MTL
      project_b code GC-B, Head = head_b_u, activity MTL
      lead_u    Lead of TAG ESTIMATION on project_a
      emp_u     plain contributor on project_a
    """
    class S:
        pass

    s = S()
    s.pm = make_user("pm@x.com", role=UserRole.project_manager)

    s.project_a = make_project(code="GC-A", name="Alpha", status=ProjectStatus.active)
    s.project_b = make_project(code="GC-B", name="Bravo", status=ProjectStatus.active)

    s.head_u = make_user("head@x.com", role=UserRole.employee)
    s.head_e = make_employee(employee_code="H-1", first_name="Hema",
                             last_name="Rao", user_id=s.head_u.id)
    proj_svc.set_project_head(db, s.pm, s.project_a.id, s.head_e.id)

    s.head_b_u = make_user("headb@x.com", role=UserRole.employee)
    s.head_b_e = make_employee(employee_code="H-2", first_name="Bala",
                               last_name="Nathan", user_id=s.head_b_u.id)
    proj_svc.set_project_head(db, s.pm, s.project_b.id, s.head_b_e.id)

    s.tag_est = _activity(db, "TAG ESTIMATION")
    s.mtl = _activity(db, "MTL")

    s.lead_u = make_user("lead@x.com", role=UserRole.employee)
    s.lead_e = make_employee(employee_code="L-1", first_name="Santhosh",
                             last_name="Kumar", user_id=s.lead_u.id)

    for activity in (s.tag_est, s.mtl):
        proj_svc.assign_activity_member(
            db, s.pm, s.project_a.id, activity.id,
            ActivityMemberCreate(employee_id=s.lead_e.id, role="lead"),
        )
    proj_svc.assign_activity_member(
        db, s.pm, s.project_b.id, s.mtl.id,
        ActivityMemberCreate(employee_id=s.lead_e.id, role="lead"),
    )

    s.emp_u = make_user("emp@x.com", role=UserRole.employee)
    s.emp_e = make_employee(employee_code="C-1", user_id=s.emp_u.id)
    proj_svc.assign_activity_member(
        db, s.pm, s.project_a.id, s.tag_est.id,
        ActivityMemberCreate(employee_id=s.emp_e.id, role="contributor"),
    )
    return s


# --- 1. PM can read the report ----------------------------------------------

def test_project_manager_can_read_report(db, scene):
    ps_svc.create_production_status(
        db, scene.pm, scene.project_a.id,
        _payload(scene.tag_est.id, tag_count=225, status="closed",
                 completed_on=date(2025, 12, 5), remarks="Issued to client."),
    )
    report = ps_svc.cumulative_report(db, scene.pm)

    assert report["row_count"] == 1
    assert report["generated_at"] is not None
    row = _rows(report)[0]
    assert row.serial == 1
    assert row.project_code == "GC-A"
    assert row.revision == "REV-0"
    assert row.activity == "TAG ESTIMATION"
    assert row.status == "closed"
    assert row.status_label == "CLOSED"
    assert row.tag_count == 225
    assert row.completed_on == date(2025, 12, 5)
    assert row.remarks == "Issued to client."


# --- 2. Head / Lead / employee get 403 --------------------------------------

def test_non_pm_roles_are_rejected(db, scene):
    """Project-scoped read authority is deliberately NOT report authority."""
    ps_svc.create_production_status(
        db, scene.pm, scene.project_a.id, _payload(scene.tag_est.id, tag_count=10)
    )

    for actor in (scene.head_u, scene.lead_u, scene.emp_u):
        with pytest.raises(AppError) as ei:
            ps_svc.cumulative_report(db, actor)
        assert ei.value.status_code == 403

    # ...while their existing project-level access is untouched. The Head still
    # reads their own project's tab, and the Lead still reads theirs.
    assert len(ps_svc.list_latest(db, scene.head_u, scene.project_a.id)) == 1
    assert len(ps_svc.list_latest(db, scene.lead_u, scene.project_a.id)) == 1


# --- 3. the same 403 over HTTP ----------------------------------------------

def test_report_endpoints_are_pm_only_over_http(db, scene, client, login):
    ps_svc.create_production_status(
        db, scene.pm, scene.project_a.id, _payload(scene.tag_est.id, tag_count=10)
    )

    for email in ("head@x.com", "lead@x.com", "emp@x.com"):
        hdr = login(email)
        assert client.get(REPORT_URL, headers=hdr).status_code == 403
        assert client.get(XLSX_URL, headers=hdr).status_code == 403

    pm_hdr = login("pm@x.com")
    assert client.get(REPORT_URL, headers=pm_hdr).status_code == 200
    assert client.get(XLSX_URL, headers=pm_hdr).status_code == 200


# --- 4. multiple projects ----------------------------------------------------

def test_report_spans_every_project(db, scene):
    ps_svc.create_production_status(
        db, scene.pm, scene.project_a.id, _payload(scene.tag_est.id, tag_count=225)
    )
    ps_svc.create_production_status(
        db, scene.pm, scene.project_b.id, _payload(scene.mtl.id, doc_count=40)
    )

    report = ps_svc.cumulative_report(db, scene.pm)
    assert report["row_count"] == 2
    assert {r.project_code for r in _rows(report)} == {"GC-A", "GC-B"}
    # Ordered by project code, and S.NO follows that one ordering.
    assert [r.serial for r in _rows(report)] == [1, 2]
    assert [r.project_code for r in _rows(report)] == ["GC-A", "GC-B"]


# --- 5. multiple activities in one project -----------------------------------

def test_report_includes_every_activity(db, scene):
    ps_svc.create_production_status(
        db, scene.pm, scene.project_a.id, _payload(scene.tag_est.id, tag_count=225)
    )
    ps_svc.create_production_status(
        db, scene.pm, scene.project_a.id, _payload(scene.mtl.id, doc_count=12)
    )

    report = ps_svc.cumulative_report(db, scene.pm)
    assert report["row_count"] == 2
    assert {r.activity for r in _rows(report)} == {"TAG ESTIMATION", "MTL"}


# --- 6. REV-0 and REV-1 are separate rows ------------------------------------

def test_both_revisions_appear(db, scene):
    """A revision is part of the row's identity, not a version of it."""
    ps_svc.create_production_status(
        db, scene.pm, scene.project_a.id,
        _payload(scene.mtl.id, revision="REV-0", tag_count=100, status="closed"),
    )
    ps_svc.create_production_status(
        db, scene.pm, scene.project_a.id,
        _payload(scene.mtl.id, revision="REV-1", tag_count=15),
    )

    report = ps_svc.cumulative_report(db, scene.pm)
    assert report["row_count"] == 2
    assert {r.revision for r in _rows(report)} == {"REV-0", "REV-1"}
    # REV-0 is NOT discarded because a newer revision exists.
    rev0 = _find(report, project_code="GC-A", revision="REV-0", activity="MTL")
    rev1 = _find(report, project_code="GC-A", revision="REV-1", activity="MTL")
    assert rev0.tag_count == 100 and rev0.status_label == "CLOSED"
    assert rev1.tag_count == 15 and rev1.status_label == "IN PROGRESS"


# --- 7. only the latest row per project + revision + activity ----------------

def test_only_latest_row_per_combination(db, scene):
    for tag, status in ((180, "in_progress"), (210, "in_progress"), (225, "closed")):
        ps_svc.create_production_status(
            db, scene.pm, scene.project_a.id,
            _payload(scene.tag_est.id, tag_count=tag, status=status,
                     completed_on=date(2025, 12, 5) if status == "closed" else None),
        )

    report = ps_svc.cumulative_report(db, scene.pm)
    assert report["row_count"] == 1
    row = _rows(report)[0]
    assert row.tag_count == 225
    assert row.status_label == "CLOSED"

    # The superseded updates are still in the trail - the report passed over
    # them, it did not remove them.
    assert len(ps_svc.list_history(db, scene.pm, scene.project_a.id)) == 3

    # And it is the SAME "latest" the project tab shows.
    latest = ps_svc.list_latest(db, scene.pm, scene.project_a.id)
    assert [(r.revision, r.activity_id, r.tag_count) for r in latest] == [
        (row.revision, row.activity_id, row.tag_count)
    ]


# --- 8. four independent counts ----------------------------------------------

def test_counts_are_four_independent_values(db, scene):
    ps_svc.create_production_status(
        db, scene.pm, scene.project_a.id,
        _payload(scene.tag_est.id, tag_count=225, doc_count=12,
                 spares_count=7, crs_count=3),
    )
    row = _rows(ps_svc.cumulative_report(db, scene.pm))[0]
    assert (row.tag_count, row.doc_count, row.spares_count, row.crs_count) == (
        225, 12, 7, 3,
    )
    # No combined total is exposed anywhere on the row.
    assert not [f for f in row.model_dump() if "total" in f]


# --- 9. BY is the actual person ----------------------------------------------

def test_by_is_the_actual_person_name(db, scene):
    """Never "PM", "Project Head" or "Activity Lead" - always the person."""
    ps_svc.create_production_status(
        db, scene.lead_u, scene.project_a.id, _payload(scene.tag_est.id, tag_count=225)
    )
    ps_svc.create_production_status(
        db, scene.head_u, scene.project_a.id, _payload(scene.mtl.id, doc_count=4)
    )

    report = ps_svc.cumulative_report(db, scene.pm)
    by = {r.activity: r.by for r in _rows(report)}
    assert by["TAG ESTIMATION"] == "Santhosh Kumar"
    assert by["MTL"] == "Hema Rao"
    assert not {"PM", "Project Head", "Activity Lead"} & set(by.values())


# --- 10. null completed_on stays null ----------------------------------------

def test_null_completed_on_stays_null(db, scene):
    ps_svc.create_production_status(
        db, scene.pm, scene.project_a.id, _payload(scene.tag_est.id, tag_count=180)
    )
    row = _rows(ps_svc.cumulative_report(db, scene.pm))[0]
    assert row.completed_on is None

    # ...and the workbook leaves the cell genuinely empty, not "-" and not a
    # date somebody guessed.
    ws = _sheet(ps_svc.cumulative_report(db, scene.pm))
    assert ws.cell(row=2, column=10).value is None


# --- 11. remarks are preserved in full ---------------------------------------

def test_full_remarks_are_preserved(db, scene):
    remark = (
        "Tag estimation completed for all 225 tags across the three units.\n"
        "Punch list received from the client on 02-Dec and closed on 04-Dec.\n"
        "Awaiting formal sign-off before the revision is frozen."
    )
    ps_svc.create_production_status(
        db, scene.pm, scene.project_a.id,
        _payload(scene.tag_est.id, tag_count=225, remarks=remark),
    )
    report = ps_svc.cumulative_report(db, scene.pm)
    assert _rows(report)[0].remarks == remark

    # Untruncated in the workbook too - the column is wrapped, not clipped.
    ws = _sheet(report)
    assert ws.cell(row=2, column=11).value == remark
    assert ws.cell(row=2, column=11).alignment.wrap_text is True


# --- 12. zero counts stay numeric zero ---------------------------------------

def test_zero_counts_stay_numeric_zero(db, scene):
    """A 0 must reach Excel as the NUMBER 0, never as "-".

    A text placeholder in one cell would break sorting, filtering and SUM() for
    the whole column - which is the entire point of exporting a spreadsheet.
    """
    ps_svc.create_production_status(
        db, scene.pm, scene.project_a.id,
        _payload(scene.tag_est.id, tag_count=225, doc_count=0,
                 spares_count=0, crs_count=0),
    )
    report = ps_svc.cumulative_report(db, scene.pm)
    row = _rows(report)[0]
    assert (row.doc_count, row.spares_count, row.crs_count) == (0, 0, 0)

    ws = _sheet(report)
    for column in (6, 7, 8, 9):          # TAG, DOC, SPARES, CRS
        value = ws.cell(row=2, column=column).value
        assert isinstance(value, int), f"column {column} is {value!r}, not an int"
    assert [ws.cell(row=2, column=c).value for c in (6, 7, 8, 9)] == [225, 0, 0, 0]


# --- 13. PROJECT / PLANT -----------------------------------------------------

def test_project_plant_uses_project_information(db, scene):
    """The existing project display convention, from existing project data."""
    planning = PlanningPlant(code="1100", description="Chennai Planning")
    db.add(planning)
    db.flush()
    maintenance = MaintenancePlant(
        code="1102", description="Chennai Works", planning_plant_id=planning.id
    )
    db.add(maintenance)
    db.flush()

    scene.project_a.planning_plant_id = planning.id
    scene.project_b.maintenance_plant_id = maintenance.id
    db.commit()

    ps_svc.create_production_status(
        db, scene.pm, scene.project_a.id, _payload(scene.tag_est.id, tag_count=1)
    )
    ps_svc.create_production_status(
        db, scene.pm, scene.project_b.id, _payload(scene.mtl.id, tag_count=2)
    )

    plants = {r.project_code: r.project_plant for r in _rows(ps_svc.cumulative_report(db, scene.pm))}
    # Planning Plant when that is all the project has...
    assert plants["GC-A"] == "GC-A / 1100"
    # ...and the more specific Maintenance Plant when the project carries one.
    assert plants["GC-B"] == "GC-B / 1102"


def test_project_plant_falls_back_to_the_code(db, scene):
    """A project with no plant still names itself - never a blank cell."""
    ps_svc.create_production_status(
        db, scene.pm, scene.project_a.id, _payload(scene.tag_est.id, tag_count=1)
    )
    assert _rows(ps_svc.cumulative_report(db, scene.pm))[0].project_plant == "GC-A"


# --- 14. empty report --------------------------------------------------------

def test_empty_report(db, scene, client, login):
    """No records is a valid report, not an error."""
    report = ps_svc.cumulative_report(db, scene.pm)
    assert report["row_count"] == 0
    assert report["rows"] == []

    res = client.get(REPORT_URL, headers=login("pm@x.com"))
    assert res.status_code == 200
    assert res.json()["rows"] == []
    assert res.json()["row_count"] == 0

    # The workbook is still a valid file with its header row.
    ws = _sheet(report)
    assert ws.max_row == 1
    assert ws.cell(row=1, column=1).value == "S.NO"


# --- 15. the workbook IS the preview dataset ---------------------------------

def _sheet(report):
    """Render the report dict to a workbook and hand back the sheet."""
    payload = {**report, "rows": [r.model_dump() for r in report["rows"]]}
    buf = export.build_production_status_report_workbook(payload)
    return openpyxl.load_workbook(buf).active


def test_workbook_matches_the_report_dataset(db, scene):
    """Every preview row, in the same order, with the same values."""
    ps_svc.create_production_status(
        db, scene.pm, scene.project_a.id,
        _payload(scene.tag_est.id, tag_count=225, status="closed",
                 completed_on=date(2025, 12, 5), remarks="Closed."),
    )
    ps_svc.create_production_status(
        db, scene.pm, scene.project_a.id,
        _payload(scene.mtl.id, revision="REV-1", doc_count=12),
    )
    ps_svc.create_production_status(
        db, scene.pm, scene.project_b.id, _payload(scene.mtl.id, spares_count=7)
    )

    report = ps_svc.cumulative_report(db, scene.pm)
    ws = _sheet(report)

    assert ws.max_row == report["row_count"] + 1        # + the header row
    for offset, row in enumerate(_rows(report)):
        excel_row = offset + 2
        assert ws.cell(row=excel_row, column=1).value == row.serial
        assert ws.cell(row=excel_row, column=2).value == row.project_plant
        assert ws.cell(row=excel_row, column=3).value == row.revision
        assert ws.cell(row=excel_row, column=4).value == row.activity
        assert ws.cell(row=excel_row, column=5).value == row.status_label
        assert ws.cell(row=excel_row, column=6).value == row.tag_count
        assert ws.cell(row=excel_row, column=7).value == row.doc_count
        assert ws.cell(row=excel_row, column=8).value == row.spares_count
        assert ws.cell(row=excel_row, column=9).value == row.crs_count
        completed = ws.cell(row=excel_row, column=10).value
        assert (completed.date() if completed else None) == row.completed_on
        assert (ws.cell(row=excel_row, column=11).value or None) == row.remarks
        assert ws.cell(row=excel_row, column=12).value == row.by

    # Sequential S.NO with no gaps.
    assert [ws.cell(row=r, column=1).value for r in range(2, ws.max_row + 1)] == [1, 2, 3]


# --- 16. workbook columns + formatting ---------------------------------------

def test_workbook_columns_and_formatting(db, scene):
    ps_svc.create_production_status(
        db, scene.pm, scene.project_a.id,
        _payload(scene.tag_est.id, tag_count=225, status="closed",
                 completed_on=date(2025, 12, 5), remarks="Issued."),
    )
    report = ps_svc.cumulative_report(db, scene.pm)
    payload = {**report, "rows": [r.model_dump() for r in report["rows"]]}
    wb = openpyxl.load_workbook(export.build_production_status_report_workbook(payload))
    ws = wb.active

    assert ws.title == "Production Status"
    assert [ws.cell(row=1, column=c).value for c in range(1, 13)] == [
        "S.NO", "PROJECT / PLANT", "REVISION", "ACTIVITY", "PROJECT STATUS",
        # Four separate count columns, never merged into one "COUNT" cell.
        "TAG", "DOC", "SPARES", "CRS",
        "COMPLETED ON", "REMARKS", "BY",
    ]
    assert ws.max_column == 12
    assert len(ws.merged_cells.ranges) == 0

    # Bold header, frozen header row, autofilter over every column.
    assert ws.cell(row=1, column=1).font.bold is True
    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref == "A1:L2"

    # Reasonable, explicitly-set column widths.
    assert ws.column_dimensions["B"].width >= 20      # PROJECT / PLANT
    assert ws.column_dimensions["K"].width >= 40      # REMARKS

    # DD-MMM-YYYY on a real date cell, and wrapped remarks.
    completed = ws.cell(row=2, column=10)
    assert completed.number_format == "DD-MMM-YYYY"
    assert completed.value.date() == date(2025, 12, 5)
    assert ws.cell(row=2, column=11).alignment.wrap_text is True


# --- 17. the download is a valid .xlsx ---------------------------------------

def test_download_produces_a_valid_xlsx(db, scene, client, login):
    ps_svc.create_production_status(
        db, scene.pm, scene.project_a.id,
        _payload(scene.tag_est.id, tag_count=225, status="closed",
                 completed_on=date(2025, 12, 5)),
    )
    res = client.get(XLSX_URL, headers=login("pm@x.com"))

    assert res.status_code == 200
    assert res.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment;" in res.headers["content-disposition"]
    assert res.headers["content-disposition"].endswith('.xlsx"')
    # A real ZIP-based OOXML file, openable by openpyxl.
    assert res.content[:2] == b"PK"
    ws = openpyxl.load_workbook(BytesIO(res.content)).active
    assert ws.title == "Production Status"
    assert ws.cell(row=2, column=6).value == 225

    # The downloaded file holds exactly the rows the preview endpoint served.
    preview = client.get(REPORT_URL, headers=login("pm@x.com")).json()
    assert ws.max_row == preview["row_count"] + 1
    assert ws.cell(row=2, column=2).value == preview["rows"][0]["project_plant"]


# --- 18. the report is not a history export ----------------------------------

def test_report_never_returns_history_rows(db, scene):
    """Cumulative means "one current row each", not "the whole trail"."""
    for tag in (10, 20, 30, 40):
        ps_svc.create_production_status(
            db, scene.pm, scene.project_a.id, _payload(scene.tag_est.id, tag_count=tag)
        )

    report = ps_svc.cumulative_report(db, scene.pm)
    assert report["row_count"] == 1
    assert _rows(report)[0].tag_count == 40

    # History is untouched and still complete inside the project.
    history = ps_svc.list_history(db, scene.pm, scene.project_a.id)
    assert [h.tag_count for h in history] == [40, 30, 20, 10]
