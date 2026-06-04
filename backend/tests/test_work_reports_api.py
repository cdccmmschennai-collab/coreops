"""API tests for the Daily Work Reports module (Phase B5).

Focus: routing, HTTP status codes, the coarse RBAC gate (require_role), response
serialization (incl. task lines), pagination, filtering, and the workflow over
HTTP. Deep business-rule coverage lives in test_work_reports_service.py.
"""
import uuid
from datetime import date, timedelta

import pytest

from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole

BASE = "/api/v1/work-reports"
TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


def _payload(project_id, report_date=TODAY, minutes=120, summary=None):
    return {
        "report_date": report_date,
        "summary": summary,
        "tasks": [
            {"project_id": str(project_id), "description": "work", "minutes_spent": minutes}
        ],
    }


@pytest.fixture()
def setup_author(make_user, make_employee, make_project, make_project_member, login):
    def _make(
        *,
        email="emp@x.com",
        code="E-1",
        role=UserRole.employee,
        manager_id=None,
        proj_code="P-1",
    ):
        u = make_user(email, role=role)
        e = make_employee(employee_code=code, user_id=u.id, manager_id=manager_id)
        p = make_project(code=proj_code, status=ProjectStatus.active)
        make_project_member(project_id=p.id, employee_id=e.id)
        return {"user": u, "emp": e, "project": p, "header": login(email)}

    return _make


# ---------- create ----------------------------------------------------------
def test_create_returns_201_with_tasks_and_draft(client, setup_author):
    a = setup_author()
    res = client.post(BASE, headers=a["header"], json=_payload(a["project"].id))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "draft"
    assert body["total_minutes"] == 120
    assert len(body["tasks"]) == 1
    assert body["tasks"][0]["minutes_spent"] == 120
    assert body["employee_id"] == str(a["emp"].id)


def test_create_requires_auth_401(client, setup_author):
    a = setup_author()
    res = client.post(BASE, json=_payload(a["project"].id))
    assert res.status_code == 401


def test_employee_without_profile_gets_422(client, make_user, login, make_project):
    # An employee user with no linked employee profile cannot file a report
    make_user("noprofile@x.com", role=UserRole.employee)
    p = make_project(code="P-1", status=ProjectStatus.active)
    res = client.post(BASE, headers=login("noprofile@x.com"), json=_payload(p.id))
    assert res.status_code == 422


def test_create_duplicate_409(client, setup_author):
    a = setup_author()
    assert client.post(BASE, headers=a["header"], json=_payload(a["project"].id)).status_code == 201
    assert client.post(BASE, headers=a["header"], json=_payload(a["project"].id)).status_code == 409


def test_create_future_date_422(client, setup_author):
    a = setup_author()
    future = (date.today() + timedelta(days=1)).isoformat()
    res = client.post(BASE, headers=a["header"], json=_payload(a["project"].id, report_date=future))
    assert res.status_code == 422


def test_create_invalid_minutes_422(client, setup_author):
    # minutes_spent=0 is now valid; -1 is still invalid
    a = setup_author()
    res = client.post(BASE, headers=a["header"], json=_payload(a["project"].id, minutes=-1))
    assert res.status_code == 422


def test_create_with_zero_minutes_succeeds(client, setup_author):
    a = setup_author()
    res = client.post(BASE, headers=a["header"], json=_payload(a["project"].id, minutes=0))
    assert res.status_code == 201
    assert res.json()["total_minutes"] == 0


def test_create_with_null_minutes_succeeds(client, setup_author):
    a = setup_author()
    payload = {
        "report_date": TODAY,
        "tasks": [{"project_id": str(a["project"].id), "description": "work", "minutes_spent": None}],
    }
    res = client.post(BASE, headers=a["header"], json=payload)
    assert res.status_code == 201
    assert res.json()["total_minutes"] == 0
    assert res.json()["tasks"][0]["minutes_spent"] is None


def test_create_with_day_status_and_location(client, setup_author):
    a = setup_author()
    payload = {
        "report_date": TODAY,
        "day_status": "wfh",
        "location": "chennai",
        "remarks": "Working from home today",
        "query_text": "Need access to the server",
        "tasks": [{"project_id": str(a["project"].id), "description": "work", "minutes_spent": 60}],
    }
    res = client.post(BASE, headers=a["header"], json=payload)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["day_status"] == "wfh"
    assert body["location"] == "chennai"
    assert body["remarks"] == "Working from home today"
    assert body["query_text"] == "Need access to the server"


def test_create_with_task_counts(client, setup_author):
    a = setup_author()
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(a["project"].id),
            "description": "maintenance",
            "activity_type": "Inspection",
            "tags_count": 5,
            "docs_count": 2,
            "bom_count": 1,
            "spares_count": 3,
        }],
    }
    res = client.post(BASE, headers=a["header"], json=payload)
    assert res.status_code == 201, res.text
    task = res.json()["tasks"][0]
    assert task["activity_type"] == "Inspection"
    assert task["tags_count"] == 5
    assert task["docs_count"] == 2
    assert task["bom_count"] == 1
    assert task["spares_count"] == 3


# ---------- list: pagination + filters -------------------------------------
def test_list_pagination(client, setup_author):
    a = setup_author()
    client.post(BASE, headers=a["header"], json=_payload(a["project"].id, report_date=TODAY))
    client.post(BASE, headers=a["header"], json=_payload(a["project"].id, report_date=YESTERDAY))
    res = client.get(f"{BASE}?limit=1&offset=0", headers=a["header"])
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert body["limit"] == 1


def test_list_filter_by_status_and_project(client, setup_author, make_project):
    a = setup_author()
    r = client.post(BASE, headers=a["header"], json=_payload(a["project"].id, report_date=TODAY)).json()
    client.post(BASE, headers=a["header"], json=_payload(a["project"].id, report_date=YESTERDAY))
    client.post(f"{BASE}/{r['id']}/submit", headers=a["header"])

    submitted = client.get(f"{BASE}?status=submitted", headers=a["header"]).json()
    assert submitted["total"] == 1
    assert submitted["items"][0]["id"] == r["id"]

    by_project = client.get(f"{BASE}?project_id={a['project'].id}", headers=a["header"]).json()
    assert by_project["total"] == 2
    none = client.get(f"{BASE}?project_id={uuid.uuid4()}", headers=a["header"]).json()
    assert none["total"] == 0


# ---------- get scoping -----------------------------------------------------
def test_get_cross_employee_403_and_missing_404(client, setup_author):
    a = setup_author(email="a@x.com", code="E-1", proj_code="P-1")
    b = setup_author(email="b@x.com", code="E-2", proj_code="P-2")
    r = client.post(BASE, headers=a["header"], json=_payload(a["project"].id)).json()

    assert client.get(f"{BASE}/{r['id']}", headers=a["header"]).status_code == 200
    assert client.get(f"{BASE}/{r['id']}", headers=b["header"]).status_code == 403
    assert client.get(f"{BASE}/{uuid.uuid4()}", headers=a["header"]).status_code == 404


# ---------- workflow over HTTP ----------------------------------------------
def test_full_workflow_create_submit_approve(client, setup_author, make_user, login):
    a = setup_author()
    make_user("admin@x.com", role=UserRole.project_manager)
    admin_h = login("admin@x.com")

    r = client.post(BASE, headers=a["header"], json=_payload(a["project"].id)).json()
    submitted = client.post(f"{BASE}/{r['id']}/submit", headers=a["header"])
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"

    approved = client.post(f"{BASE}/{r['id']}/approve", headers=admin_h)
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


def test_reject_requires_note_then_resubmit(client, setup_author, make_user, login):
    a = setup_author()
    make_user("admin@x.com", role=UserRole.project_manager)
    admin_h = login("admin@x.com")
    r = client.post(BASE, headers=a["header"], json=_payload(a["project"].id)).json()
    client.post(f"{BASE}/{r['id']}/submit", headers=a["header"])

    # empty note rejected by schema
    bad = client.post(f"{BASE}/{r['id']}/reject", headers=admin_h, json={"review_note": ""})
    assert bad.status_code == 422

    ok = client.post(f"{BASE}/{r['id']}/reject", headers=admin_h, json={"review_note": "redo"})
    assert ok.status_code == 200 and ok.json()["status"] == "rejected"

    resub = client.post(f"{BASE}/{r['id']}/submit", headers=a["header"])
    assert resub.status_code == 200 and resub.json()["status"] == "submitted"


def test_employee_cannot_approve_403(client, setup_author):
    a = setup_author()
    r = client.post(BASE, headers=a["header"], json=_payload(a["project"].id)).json()
    client.post(f"{BASE}/{r['id']}/submit", headers=a["header"])
    # employee hits the review gate -> 403
    assert client.post(f"{BASE}/{r['id']}/approve", headers=a["header"]).status_code == 403


def test_any_project_manager_can_approve(
    client, make_user, make_employee, make_project, make_project_member, login
):
    m1 = make_user("m1@x.com", role=UserRole.project_manager)
    m1_emp = make_employee(employee_code="M-1", user_id=m1.id)
    m2 = make_user("m2@x.com", role=UserRole.project_manager)
    make_employee(employee_code="M-2", user_id=m2.id)

    emp_user = make_user("e@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E-1", user_id=emp_user.id, manager_id=m1_emp.id)
    p = make_project(code="P-1", status=ProjectStatus.active)
    make_project_member(project_id=p.id, employee_id=emp.id)

    r = client.post(BASE, headers=login("e@x.com"), json=_payload(p.id)).json()
    client.post(f"{BASE}/{r['id']}/submit", headers=login("e@x.com"))

    # ANY project_manager can approve (no team scoping)
    assert client.post(f"{BASE}/{r['id']}/approve", headers=login("m2@x.com")).status_code == 200


# ---------- edit + delete ---------------------------------------------------
def test_patch_author_ok_non_author_403(client, setup_author):
    a = setup_author(email="a@x.com", code="E-1", proj_code="P-1")
    b = setup_author(email="b@x.com", code="E-2", proj_code="P-2")
    r = client.post(BASE, headers=a["header"], json=_payload(a["project"].id)).json()

    ok = client.patch(f"{BASE}/{r['id']}", headers=a["header"], json={"summary": "updated"})
    assert ok.status_code == 200 and ok.json()["summary"] == "updated"
    assert client.patch(f"{BASE}/{r['id']}", headers=b["header"], json={"summary": "x"}).status_code == 403


def test_delete_draft_204_submitted_403(client, setup_author):
    a = setup_author()
    r1 = client.post(BASE, headers=a["header"], json=_payload(a["project"].id, report_date=TODAY)).json()
    assert client.delete(f"{BASE}/{r1['id']}", headers=a["header"]).status_code == 204

    r2 = client.post(BASE, headers=a["header"], json=_payload(a["project"].id, report_date=YESTERDAY)).json()
    client.post(f"{BASE}/{r2['id']}/submit", headers=a["header"])
    assert client.delete(f"{BASE}/{r2['id']}", headers=a["header"]).status_code == 403


# ---------- OpenAPI integration --------------------------------------------
def test_openapi_exposes_work_reports_paths(client):
    spec = client.get("/api/v1/openapi.json").json()
    paths = spec["paths"]
    assert "/api/v1/work-reports" in paths
    assert "/api/v1/work-reports/{report_id}" in paths
    assert "/api/v1/work-reports/{report_id}/submit" in paths
    assert "/api/v1/work-reports/{report_id}/approve" in paths
    assert "/api/v1/work-reports/{report_id}/reject" in paths
