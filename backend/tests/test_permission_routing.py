"""Phase 4B - Permission Request routing to Project Head.

Permission reuses `leave/routing.py::resolve_routed_project` unchanged - that
resolver's own exhaustive matrix (working-day walk, ambiguity, staleness, a
Head's own request) is already covered by `test_leave_routing.py` and is not
repeated here. These tests pin PERMISSION's own integration of it: the
create flow stores the result, the fallback reads `reporting_pm_id` (never
`manager_id`), and review authority actually follows the routed Head.

    docker exec wms-backend-1 pytest tests/test_permission_routing.py
"""
from datetime import date, timedelta

from app.modules.calendar.models import CalendarEvent, CalendarEventType
from app.modules.calendar.working_days import previous_working_day
from app.modules.permissions import service as perm_svc
from app.modules.permissions.models import (
    PermissionPeriod,
    PermissionRequest,
    PermissionStatus,
)
from app.modules.permissions.schemas import PermissionRequestCreate
from app.modules.users.models import UserRole
from app.modules.work_reports import service as wr_svc
from app.modules.work_reports.models import DayStatus
from app.modules.work_reports.schemas import WorkReportCreate, WorkReportTaskIn

API = "/api/v1/permission-requests"

# A working Monday far enough in the future that its month is never "closed"
# (see `_assert_month_open`) - the same constant `test_permissions_phase11.py`
# already established for this reason.
PERMISSION_DATE = date(2027, 3, 1)

# Maps the old `hours` shorthand this file's tests use onto a period - routing
# tests care about the routed project, not which half was picked, so any period
# costing that many hours is an equally valid stand-in.
_PERIOD_FOR_HOURS = {
    1: PermissionPeriod.first_half_1h,
    2: PermissionPeriod.first_half_2h,
}


def _task(project_id, minutes=120):
    return WorkReportTaskIn(project_id=project_id, description="work", minutes_spent=minutes)


def _working_days_back(db, count: int) -> list[date]:
    """The last `count` working days at-or-before real "today", most recent
    first - report evidence must be dated in the past (`work_reports.service`
    refuses a future report), unlike `PERMISSION_DATE` itself.
    """
    days: list[date] = []
    cursor = date.today() + timedelta(days=1)
    for _ in range(count):
        cursor = previous_working_day(db, cursor)
        assert cursor is not None, "no working day found - calendar misconfigured"
        days.append(cursor)
    return days


def _close_the_office(db, day: date) -> None:
    db.add(CalendarEvent(
        event_date=day, title="Company holiday", event_type=CalendarEventType.holiday,
    ))
    db.commit()


def _submit(db, actor, day=PERMISSION_DATE, hours=1):
    return perm_svc.create_permission_request(
        db, actor,
        PermissionRequestCreate(
            permission_date=day, period=_PERIOD_FOR_HOURS[hours], reason="x"
        ),
    )


# ---------- routing resolution integrates correctly -------------------------

def test_exactly_one_project_routes_to_its_current_head(
    db, make_user, make_employee, make_project, make_project_member,
):
    head_u = make_user("phead1@x.com")
    head = make_employee(employee_code="PH-1", user_id=head_u.id)
    project = make_project(code="PR-1", head_employee_id=head.id)

    eu = make_user("pemp1@x.com")
    emp = make_employee(employee_code="PE-1", user_id=eu.id)
    make_project_member(project_id=project.id, employee_id=emp.id)
    (prev_day,) = _working_days_back(db, 1)
    wr_svc.create_work_report(
        db, eu, WorkReportCreate(report_date=prev_day, tasks=[_task(project.id)])
    )

    req = _submit(db, eu)

    assert req.routed_project_id == project.id


def test_walks_back_past_a_non_working_day_and_a_no_activity_report(
    db, make_user, make_employee, make_project, make_project_member,
):
    """The report immediately before the boundary sits on a day the office
    later gets declared shut, and the one before THAT logs no project work -
    both are skipped and the older, valid report wins."""
    eu = make_user("pemp2@x.com")
    emp = make_employee(employee_code="PE-2", user_id=eu.id)
    target = make_project(code="PR-2")
    other = make_project(code="PR-2B")
    make_project_member(project_id=target.id, employee_id=emp.id)
    make_project_member(project_id=other.id, employee_id=emp.id)

    now_closed, no_activity, older_valid = _working_days_back(db, 3)
    wr_svc.create_work_report(
        db, eu, WorkReportCreate(report_date=older_valid, tasks=[_task(target.id)])
    )
    wr_svc.create_work_report(
        db, eu, WorkReportCreate(report_date=no_activity, day_status=DayStatus.leave, tasks=[])
    )
    wr_svc.create_work_report(
        db, eu, WorkReportCreate(report_date=now_closed, tasks=[_task(other.id)])
    )
    _close_the_office(db, now_closed)

    req = _submit(db, eu)

    assert req.routed_project_id == target.id


def test_multiple_distinct_projects_falls_back(
    db, make_user, make_employee, make_project, make_project_member,
):
    eu = make_user("pemp3@x.com")
    emp = make_employee(employee_code="PE-3", user_id=eu.id)
    a = make_project(code="PR-3A")
    b = make_project(code="PR-3B")
    make_project_member(project_id=a.id, employee_id=emp.id)
    make_project_member(project_id=b.id, employee_id=emp.id)
    (prev_day,) = _working_days_back(db, 1)
    wr_svc.create_work_report(
        db, eu, WorkReportCreate(report_date=prev_day, tasks=[_task(a.id), _task(b.id, 60)])
    )

    req = _submit(db, eu)

    assert req.routed_project_id is None


def test_no_usable_report_falls_back(db, make_user, make_employee):
    eu = make_user("pemp4@x.com")
    make_employee(employee_code="PE-4", user_id=eu.id)

    req = _submit(db, eu)

    assert req.routed_project_id is None


def test_fallback_reads_reporting_pm_id_never_manager_id(db, make_user, make_employee):
    """No routed project. The line manager is NOT an authorized reviewer here
    any more than for Leave, so the recipient must be the reporting PM, never
    `employee.manager_id`."""
    line_mgr_u = make_user("linemgr@x.com")
    line_mgr = make_employee(employee_code="LM-1", user_id=line_mgr_u.id)
    pm_u = make_user("realpm@x.com", role=UserRole.project_manager)
    make_employee(employee_code="RPM-1", user_id=pm_u.id)

    eu = make_user("pemp5@x.com")
    emp = make_employee(
        employee_code="PE-5", user_id=eu.id,
        manager_id=line_mgr.id, reporting_pm_id=pm_u.id,
    )

    req = PermissionRequest(
        employee_id=emp.id, permission_date=PERMISSION_DATE, duration_hours=1,
        period=PermissionPeriod.first_half_1h,
        status=PermissionStatus.pending, routed_project_id=None,
    )
    recipient = perm_svc._routed_recipient(db, emp, req)

    assert recipient is not None
    assert recipient.user_id == pm_u.id
    assert recipient.employee_code != line_mgr.employee_code


# ---------- review authorization follows the routed Head --------------------

def test_routed_project_head_can_approve(
    db, client, login, make_user, make_employee, make_project, make_project_member,
):
    head_u = make_user("apphead@x.com")
    head = make_employee(employee_code="AH-1", user_id=head_u.id)
    project = make_project(code="PR-4", head_employee_id=head.id)

    eu = make_user("apemp@x.com")
    emp = make_employee(employee_code="AE-1", user_id=eu.id)
    make_project_member(project_id=project.id, employee_id=emp.id)
    (prev_day,) = _working_days_back(db, 1)
    wr_svc.create_work_report(
        db, eu, WorkReportCreate(report_date=prev_day, tasks=[_task(project.id)])
    )

    res = client.post(API, headers=login("apemp@x.com"), json={
        "permission_date": PERMISSION_DATE.isoformat(), "period": "first_half_1h", "reason": "x",
    })
    assert res.status_code == 201, res.text
    req_id = res.json()["id"]
    assert res.json()["routed_project_id"] == str(project.id)

    res = client.post(f"{API}/{req_id}/approve", headers=login("apphead@x.com"), json={})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"


def test_unrelated_employee_cannot_approve(
    db, client, login, make_user, make_employee, make_project, make_project_member,
):
    head_u = make_user("unrelhead@x.com")
    head = make_employee(employee_code="UH-1", user_id=head_u.id)
    project = make_project(code="PR-5", head_employee_id=head.id)

    eu = make_user("unrelemp@x.com")
    emp = make_employee(employee_code="UE-1", user_id=eu.id)
    make_project_member(project_id=project.id, employee_id=emp.id)
    (prev_day,) = _working_days_back(db, 1)
    wr_svc.create_work_report(
        db, eu, WorkReportCreate(report_date=prev_day, tasks=[_task(project.id)])
    )

    outsider_u = make_user("outsider@x.com")
    make_employee(employee_code="OUT-1", user_id=outsider_u.id)

    res = client.post(API, headers=login("unrelemp@x.com"), json={
        "permission_date": PERMISSION_DATE.isoformat(), "period": "first_half_1h", "reason": "x",
    })
    req_id = res.json()["id"]

    res = client.post(f"{API}/{req_id}/approve", headers=login("outsider@x.com"), json={})
    assert res.status_code == 403, res.text


def test_pm_fallback_still_approves_when_no_project_routed(
    db, client, login, make_user, make_employee,
):
    """No usable report -> PM fallback, unchanged from before Phase 4B."""
    pm_u = make_user("fallbackpm@x.com", role=UserRole.project_manager)
    make_employee(employee_code="FPM-1", user_id=pm_u.id)

    eu = make_user("fallbackemp@x.com")
    make_employee(employee_code="FE-1", user_id=eu.id, reporting_pm_id=pm_u.id)

    res = client.post(API, headers=login("fallbackemp@x.com"), json={
        "permission_date": PERMISSION_DATE.isoformat(), "period": "first_half_1h", "reason": "x",
    })
    assert res.status_code == 201, res.text
    req_id = res.json()["id"]
    assert res.json()["routed_project_id"] is None

    res = client.post(f"{API}/{req_id}/approve", headers=login("fallbackpm@x.com"), json={})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"


# ---------- the review QUEUE shows a Head exactly what they may review -------

def _routed_request(db, client, login, project, emp_user, emp_email):
    """File a permission that routes to `project` via yesterday's report."""
    (prev_day,) = _working_days_back(db, 1)
    wr_svc.create_work_report(
        db, emp_user, WorkReportCreate(report_date=prev_day, tasks=[_task(project.id)])
    )
    res = client.post(API, headers=login(emp_email), json={
        "permission_date": PERMISSION_DATE.isoformat(),
        "period": "first_half_1h",
        "reason": "x",
    })
    assert res.status_code == 201, res.text
    assert res.json()["routed_project_id"] == str(project.id)
    return res.json()["id"]


def test_head_lists_requests_routed_to_their_project(
    db, client, login, make_user, make_employee, make_project, make_project_member,
):
    """Phase 4D: the Permission requests queue a Head opens is the SAME endpoint
    a PM's queue calls, scoped server-side. Before this, review authority said
    yes and the list said nothing - the queue came back empty."""
    head_u = make_user("qhead@x.com")
    head = make_employee(employee_code="QH-1", user_id=head_u.id)
    project = make_project(code="PR-6", head_employee_id=head.id)

    eu = make_user("qemp@x.com")
    emp = make_employee(employee_code="QE-1", user_id=eu.id)
    make_project_member(project_id=project.id, employee_id=emp.id)
    req_id = _routed_request(db, client, login, project, eu, "qemp@x.com")

    res = client.get(f"{API}?status=pending", headers=login("qhead@x.com"))
    assert res.status_code == 200, res.text
    assert req_id in [r["id"] for r in res.json()["items"]]


def test_another_head_does_not_list_the_request(
    db, client, login, make_user, make_employee, make_project, make_project_member,
):
    """A Head heads THEIR project, not permissions generally."""
    head_u = make_user("ohead@x.com")
    head = make_employee(employee_code="OH-1", user_id=head_u.id)
    project = make_project(code="PR-7", head_employee_id=head.id)

    other_head_u = make_user("ohead2@x.com")
    other_head = make_employee(employee_code="OH-2", user_id=other_head_u.id)
    make_project(code="PR-8", head_employee_id=other_head.id)

    eu = make_user("oemp@x.com")
    emp = make_employee(employee_code="OE-1", user_id=eu.id)
    make_project_member(project_id=project.id, employee_id=emp.id)
    req_id = _routed_request(db, client, login, project, eu, "oemp@x.com")

    res = client.get(f"{API}?status=pending", headers=login("ohead2@x.com"))
    assert res.status_code == 200, res.text
    assert req_id not in [r["id"] for r in res.json()["items"]]

    res = client.post(f"{API}/{req_id}/approve", headers=login("ohead2@x.com"), json={})
    assert res.status_code == 403, res.text


def test_exclude_self_drops_the_heads_own_request_from_the_queue(
    db, client, login, make_user, make_employee, make_project, make_project_member,
):
    """Nobody reviews their own, so a Head's own request must not sit in the
    queue they work through. It stays visible WITHOUT the flag - the Head's own
    history is still theirs to read.

    The Head's own request carries no routed project (the resolver refuses to
    route a Head's request to a project they head themselves), so it reaches the
    list purely through the own-rows half of the scope - which is exactly why
    `exclude_self` and not the scope is what removes it.
    """
    head_u = make_user("shead@x.com")
    head = make_employee(employee_code="SH-1", user_id=head_u.id)
    project = make_project(code="PR-9", head_employee_id=head.id)
    make_project_member(project_id=project.id, employee_id=head.id)

    hdr = login("shead@x.com")
    res = client.post(API, headers=hdr, json={
        "permission_date": PERMISSION_DATE.isoformat(),
        "period": "first_half_1h",
        "reason": "x",
    })
    assert res.status_code == 201, res.text
    own_id = res.json()["id"]

    plain = client.get(f"{API}?status=pending", headers=hdr)
    assert own_id in [r["id"] for r in plain.json()["items"]]

    filtered = client.get(f"{API}?status=pending&exclude_self=true", headers=hdr)
    assert filtered.status_code == 200, filtered.text
    assert own_id not in [r["id"] for r in filtered.json()["items"]]

