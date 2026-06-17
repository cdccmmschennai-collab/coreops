"""Tests for the plants module: read-only list endpoints, the Project
maintenance_plant_id link + editable code, and the Work Report task row's
independent maintenance plant selection."""
from datetime import date

import pytest

from app.modules.plants.models import MaintenancePlant, PlanningPlant
from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole

PLANTS_BASE = "/api/v1/plants"
PROJECTS_BASE = "/api/v1/projects"
WR_BASE = "/api/v1/work-reports"
TODAY = date.today().isoformat()


@pytest.fixture()
def plant(db):
    pp = PlanningPlant(code="2300", description="Dukhan Planning Plant")
    db.add(pp)
    db.flush()
    mp = MaintenancePlant(code="ARBD", description='Arab "D"', planning_plant_id=pp.id)
    db.add(mp)
    db.commit()
    db.refresh(mp)
    return {"planning_plant": pp, "maintenance_plant": mp}


# ── list endpoints ──────────────────────────────────────────────────────────

def test_list_planning_plants(client, auth_header, plant):
    h = auth_header(role=UserRole.employee)
    res = client.get(f"{PLANTS_BASE}/planning-plants", headers=h)
    assert res.status_code == 200
    codes = [r["code"] for r in res.json()]
    assert "2300" in codes


def test_list_maintenance_plants_includes_parent_info(client, auth_header, plant):
    h = auth_header(role=UserRole.employee)
    res = client.get(f"{PLANTS_BASE}/maintenance-plants", headers=h)
    assert res.status_code == 200
    rows = {r["code"]: r for r in res.json()}
    assert rows["ARBD"]["planning_plant_code"] == "2300"
    assert rows["ARBD"]["planning_plant_description"] == "Dukhan Planning Plant"


def test_list_plants_requires_auth(client):
    res = client.get(f"{PLANTS_BASE}/planning-plants")
    assert res.status_code == 401


# ── project maintenance_plant_id + editable code ────────────────────────────

def test_create_project_with_maintenance_plant(client, auth_header, plant):
    h = auth_header(role=UserRole.project_manager)
    res = client.post(PROJECTS_BASE, headers=h, json={
        "code": "GC19101900", "name": "Test Project",
        "maintenance_plant_id": str(plant["maintenance_plant"].id),
    })
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["maintenance_plant_code"] == "ARBD"
    assert body["planning_plant_code"] == "2300"
    assert body["planning_plant_description"] == "Dukhan Planning Plant"


def test_project_code_is_editable(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    created = client.post(PROJECTS_BASE, headers=h, json={
        "code": "OLD-CODE", "name": "Test Project",
    }).json()
    res = client.patch(f"{PROJECTS_BASE}/{created['id']}", headers=h, json={"code": "NEW-CODE"})
    assert res.status_code == 200, res.text
    assert res.json()["code"] == "NEW-CODE"


def test_project_code_change_rejects_duplicate(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    client.post(PROJECTS_BASE, headers=h, json={"code": "DUPE-1", "name": "A"})
    p2 = client.post(PROJECTS_BASE, headers=h, json={"code": "DUPE-2", "name": "B"}).json()
    res = client.patch(f"{PROJECTS_BASE}/{p2['id']}", headers=h, json={"code": "DUPE-1"})
    assert res.status_code == 409


# ── work report task maintenance plant ──────────────────────────────────────

@pytest.fixture()
def setup_author(make_user, make_employee, make_project, make_project_member, login):
    def _make(*, email="emp@x.com", code="E-1", proj_code="P-1"):
        u = make_user(email, role=UserRole.employee)
        e = make_employee(employee_code=code, user_id=u.id)
        p = make_project(code=proj_code, status=ProjectStatus.active)
        make_project_member(project_id=p.id, employee_id=e.id)
        return {"user": u, "emp": e, "project": p, "header": login(email)}

    return _make


def test_work_report_task_snapshots_maintenance_plant(client, setup_author, plant):
    a = setup_author()
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "maintenance_plant_id": str(plant["maintenance_plant"].id),
        }],
    }
    res = client.post(WR_BASE, headers=a["header"], json=payload)
    assert res.status_code == 201, res.text
    task = res.json()["tasks"][0]
    assert task["maintenance_plant_code"] == "ARBD"
    assert task["planning_plant_code"] == "2300"
    assert task["planning_plant_description"] == "Dukhan Planning Plant"


def test_work_report_task_rejects_inactive_maintenance_plant(client, setup_author, db, plant):
    plant["maintenance_plant"].is_active = False
    db.add(plant["maintenance_plant"])
    db.commit()
    a = setup_author()
    payload = {
        "report_date": TODAY,
        "tasks": [{
            "project_id": str(a["project"].id), "description": "work",
            "maintenance_plant_id": str(plant["maintenance_plant"].id),
        }],
    }
    res = client.post(WR_BASE, headers=a["header"], json=payload)
    assert res.status_code == 422
