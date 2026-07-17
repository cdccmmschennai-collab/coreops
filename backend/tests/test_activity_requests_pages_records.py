"""Phase 2.5 — PAGES/RECORDS workload hints on the employee-to-PM Activity
Request flow (migration 0059).

activity_requests was the last place in the system stuck on four units: an
employee could not raise "please add MTL-DOC.O&M MANNUALS DATA POPULATION, 500
PAGES" without the quantity being dropped.

These counts are REQUEST HINTS, not benchmark inputs. The tests below prove both
halves of that: the values survive the round trip and reach the PM, and they
create no performance, no completion and no pending of their own — the benchmark
only ever engages once the approved row lives on the report.
"""
from datetime import date

import pytest
from sqlalchemy import select

from app.modules.activity_master.models import (
    LEVEL_ACTIVITY,
    LEVEL_SUB_ACTIVITY,
    ActivityMaster,
)
from app.modules.activity_requests import service as ar_svc
from app.modules.activity_requests.models import ActivityRequest
from app.modules.activity_requests.schemas import ActivityRequestCreate
from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole
from app.modules.work_reports import service as wr_svc
from app.modules.work_reports.models import WorkReportTask
from app.modules.work_reports.schemas import WorkReportCreate, WorkReportTaskIn

TODAY = date.today()


@pytest.fixture()
def pages_sub(db):
    """A TASK_WITH_QUANTITY page activity, configured as 0058 configures the
    real MTL rows."""
    act = ActivityMaster(name="MTL", level=LEVEL_ACTIVITY)
    db.add(act)
    db.flush()
    sub = ActivityMaster(
        name="MTL-DOC.O&M MANNUALS DATA POPULATION",
        level=LEVEL_SUB_ACTIVITY,
        parent_id=act.id,
        benchmark_type="TASK_WITH_QUANTITY",
        benchmark_value=500,
        benchmark_period_days=1,
        relevant_count_field="pages",
        benchmark_unit_note="PAGES",
        benchmark_remarks="500 REQUIRED PAGES/DAY",
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@pytest.fixture()
def records_sub(db):
    act = db.execute(
        select(ActivityMaster).where(ActivityMaster.name == "DOC IDB")
    ).scalar_one_or_none()
    if act is None:
        act = ActivityMaster(name="DOC IDB", level=LEVEL_ACTIVITY)
        db.add(act)
        db.flush()
    sub = ActivityMaster(
        name="DOC IDB-MDR/VDR CONSOLIDATION (DOC.TYPE/DOC.REQUIRED STATUS)",
        level=LEVEL_SUB_ACTIVITY,
        parent_id=act.id,
        benchmark_type="NUMERIC_DAILY",
        benchmark_value=1000,
        benchmark_period_days=1,
        relevant_count_field="records",
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@pytest.fixture()
def scenario(db, make_user, make_employee, make_project, make_project_member):
    pm_u = make_user("pm@x.com", role=UserRole.project_manager)
    make_employee(employee_code="PM-1", user_id=pm_u.id)
    emp_u = make_user("emp@x.com", role=UserRole.employee)
    emp_e = make_employee(employee_code="E-1", user_id=emp_u.id)
    project = make_project(code="P-1", status=ProjectStatus.active)
    make_project_member(project_id=project.id, employee_id=emp_e.id)
    report = wr_svc.create_work_report(
        db, emp_u,
        WorkReportCreate(
            report_date=TODAY,
            tasks=[WorkReportTaskIn(project_id=project.id, description="a",
                                    minutes_spent=60)],
        ),
    )
    return pm_u, emp_u, project, report


def _create(db, emp_u, project, report, sub, **counts):
    return ar_svc.create_request(
        db, emp_u,
        ActivityRequestCreate(
            report_id=report.id, project_id=project.id,
            activity_id=sub.parent_id, sub_activity_id=sub.id, **counts,
        ),
    )


# ── acceptance + round trip ────────────────────────────────────────────────


def test_pages_accepted_and_persisted(db, scenario, pages_sub):
    _, emp_u, project, report = scenario
    req = _create(db, emp_u, project, report, pages_sub, pages_count=500)

    assert req.pages_count == 500
    stored = db.get(ActivityRequest, req.id)
    assert stored.pages_count == 500
    assert stored.records_count == 0


def test_records_accepted_and_persisted(db, scenario, records_sub):
    _, emp_u, project, report = scenario
    req = _create(db, emp_u, project, report, records_sub, records_count=1000)

    stored = db.get(ActivityRequest, req.id)
    assert stored.records_count == 1000
    assert stored.pages_count == 0


def test_counts_default_to_zero(db, scenario, pages_sub):
    """An employee who requests an activity without a quantity gets zeros, not
    NULLs — same convention as the four original units."""
    _, emp_u, project, report = scenario
    req = _create(db, emp_u, project, report, pages_sub)

    assert (req.tags_count, req.docs_count, req.bom_count, req.spares_count) == (0, 0, 0, 0)
    assert (req.pages_count, req.records_count) == (0, 0)


def test_existing_four_units_still_work(db, scenario, pages_sub):
    _, emp_u, project, report = scenario
    req = _create(
        db, emp_u, project, report, pages_sub,
        tags_count=10, docs_count=20, bom_count=30, spares_count=40,
    )
    stored = db.get(ActivityRequest, req.id)
    assert (stored.tags_count, stored.docs_count, stored.bom_count,
            stored.spares_count) == (10, 20, 30, 40)
    assert (stored.pages_count, stored.records_count) == (0, 0)


def test_all_six_units_coexist_on_one_request(db, scenario, pages_sub):
    _, emp_u, project, report = scenario
    req = _create(
        db, emp_u, project, report, pages_sub,
        tags_count=1, docs_count=2, bom_count=3, spares_count=4,
        pages_count=5, records_count=6,
    )
    stored = db.get(ActivityRequest, req.id)
    assert (stored.tags_count, stored.docs_count, stored.bom_count,
            stored.spares_count, stored.pages_count, stored.records_count) == (
        1, 2, 3, 4, 5, 6
    )


def test_negative_counts_rejected(db, scenario, pages_sub):
    _, emp_u, project, report = scenario
    with pytest.raises(Exception):
        _create(db, emp_u, project, report, pages_sub, pages_count=-1)


# ── the PM's view ──────────────────────────────────────────────────────────


def test_pm_receives_pages_and_records_in_response(db, scenario, pages_sub):
    """The whole point of the request: the PM must see the requested workload."""
    pm_u, emp_u, project, report = scenario
    _create(db, emp_u, project, report, pages_sub, pages_count=500)

    pending = ar_svc.list_requests(db, pm_u)
    row = next(r for r in pending if r.sub_activity_id == pages_sub.id)
    assert row.pages_count == 500
    assert row.records_count == 0
    assert row.sub_activity_name == "MTL-DOC.O&M MANNUALS DATA POPULATION"


# ── approval carries the hint onto the report row ──────────────────────────


def test_approval_copies_pages_onto_the_work_report_row(db, scenario, pages_sub):
    pm_u, emp_u, project, report = scenario
    req = _create(db, emp_u, project, report, pages_sub, pages_count=500)

    ar_svc.approve_request(db, pm_u, req.id)

    row = db.execute(
        select(WorkReportTask).where(
            WorkReportTask.report_id == report.id,
            WorkReportTask.sub_activity_id == pages_sub.id,
        )
    ).scalar_one()
    assert row.pages_count == 500
    assert row.records_count == 0


def test_approval_copies_records_onto_the_work_report_row(db, scenario, records_sub):
    pm_u, emp_u, project, report = scenario
    req = _create(db, emp_u, project, report, records_sub, records_count=1000)

    ar_svc.approve_request(db, pm_u, req.id)

    row = db.execute(
        select(WorkReportTask).where(
            WorkReportTask.report_id == report.id,
            WorkReportTask.sub_activity_id == records_sub.id,
        )
    ).scalar_one()
    assert row.records_count == 1000
    assert row.docs_count == 0  # a record is not a document


# ── hints are NOT benchmark inputs ─────────────────────────────────────────


def test_request_creates_no_benchmark_performance(db, scenario, pages_sub):
    """A pending request must not produce deficit/productivity anywhere. Nothing
    is benchmarked until the work is actually reported and submitted."""
    _, emp_u, project, report = scenario
    _create(db, emp_u, project, report, pages_sub, pages_count=500)

    rows = db.execute(
        select(WorkReportTask).where(WorkReportTask.report_id == report.id)
    ).scalars().all()
    assert all(r.deficit is None for r in rows)
    assert all(r.productivity_pct is None for r in rows)
    # And the request created no activity row of its own — only approval does.
    assert all(r.sub_activity_id != pages_sub.id for r in rows)


def test_approved_row_is_open_and_uncompleted(db, scenario, pages_sub):
    """Requesting 500 pages is not progress: the approved row starts open, with
    no completion and no WorkItem completion, exactly like a row the employee
    added themselves."""
    pm_u, emp_u, project, report = scenario
    req = _create(db, emp_u, project, report, pages_sub, pages_count=500)

    ar_svc.approve_request(db, pm_u, req.id)

    row = db.execute(
        select(WorkReportTask).where(
            WorkReportTask.report_id == report.id,
            WorkReportTask.sub_activity_id == pages_sub.id,
        )
    ).scalar_one()
    assert row.is_completed is False
    assert row.completed_date is None
    # A quantity hint never pre-computes performance either — that happens at
    # submit time, from what the employee actually reports.
    assert row.deficit is None
    assert row.productivity_pct is None


def test_approval_does_not_touch_work_item_completion(db, scenario, pages_sub):
    pm_u, emp_u, project, report = scenario
    req = _create(db, emp_u, project, report, pages_sub, pages_count=500)

    ar_svc.approve_request(db, pm_u, req.id)

    from app.modules.work_reports.models import WorkItem

    items = db.execute(select(WorkItem)).scalars().all()
    assert all(i.completed_on is None for i in items)
