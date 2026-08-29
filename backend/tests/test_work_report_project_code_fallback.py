"""Project Code fallback for work reports (Support Missing Project Codes).

A project may exist with no permanent code yet (Project Master
`code IS NULL`, migration 0078 — e.g. a Tag Estimation engagement that starts
before SAP assigns one). Case 1: the project already has a code — the employee
never sees a project-code input, and the code is used automatically. Case 2:
the project has no code — the employee must type one on the activity row, and
it is saved with THAT work-report activity (work_report_tasks.project_code,
the pre-existing snapshot column from migration 0017) — never written back
into the Project Master, which stays NULL.

effective_project_code = project.code OR employee_entered `manual_project_code`.
Both missing -> 422.
"""
from datetime import date

import pytest

from app.core.database import SessionLocal
from app.modules.projects.models import Project, ProjectStatus
from app.modules.users.models import UserRole

BASE = "/api/v1/work-reports"
TODAY = date.today().isoformat()


@pytest.fixture()
def setup_author(make_user, make_employee, make_project, make_project_member, login):
    def _make(*, email="emp@x.com", code="E-1", project_code="P-1"):
        u = make_user(email, role=UserRole.employee)
        e = make_employee(employee_code=code, user_id=u.id)
        p = make_project(code=project_code, status=ProjectStatus.active)
        make_project_member(project_id=p.id, employee_id=e.id)
        return {"user": u, "emp": e, "project": p, "header": login(email)}

    return _make


@pytest.fixture()
def pm_header(auth_header):
    return auth_header(email="pm@x.com", role=UserRole.project_manager)


def _task(project_id, **overrides):
    body = {
        "project_id": str(project_id),
        "description": "work",
        "count_field": "tags",
        "count_value": 1,
    }
    body.update(overrides)
    return body


def _create(client, header, tasks, *, report_date=TODAY):
    return client.post(
        BASE,
        headers=header,
        json={
            "report_date": report_date,
            "day_status": "work_at_office",
            "location": "chennai",
            "tasks": tasks,
        },
    )


# ── 1 & 6: project already has a code ───────────────────────────────────────

def test_project_with_code_uses_project_code_automatically(client, setup_author):
    a = setup_author(project_code="4391-GC21107300")
    res = _create(client, a["header"], [_task(a["project"].id)])
    assert res.status_code == 201, res.text
    task = res.json()["tasks"][0]
    assert task["project_code"] == "4391-GC21107300"


def test_project_with_code_does_not_require_manual_entry(client, setup_author):
    """A manual_project_code sent alongside a coded project is simply ignored —
    the project's own code always wins."""
    a = setup_author(project_code="4391-GC21107300")
    res = _create(
        client, a["header"],
        [_task(a["project"].id, manual_project_code="SOMETHING-ELSE")],
    )
    assert res.status_code == 201, res.text
    assert res.json()["tasks"][0]["project_code"] == "4391-GC21107300"


# ── 2, 3, 4: project has NO code ────────────────────────────────────────────

def test_project_without_code_and_no_manual_entry_rejected(client, setup_author):
    a = setup_author(project_code=None)
    res = _create(client, a["header"], [_task(a["project"].id)])
    assert res.status_code == 422, res.text


def test_project_without_code_with_manual_entry_saves(client, setup_author):
    a = setup_author(project_code=None)
    res = _create(
        client, a["header"],
        [_task(a["project"].id, manual_project_code="TAG-EST-2026")],
    )
    assert res.status_code == 201, res.text
    task = res.json()["tasks"][0]
    assert task["project_code"] == "TAG-EST-2026"


def test_project_without_code_manual_entry_is_trimmed_and_blank_is_rejected(
    client, setup_author
):
    """Whitespace-only entry is treated as missing, exactly like an empty
    string — the employee has not actually named a code."""
    a = setup_author(project_code=None)
    res = _create(
        client, a["header"],
        [_task(a["project"].id, manual_project_code="   ")],
    )
    assert res.status_code == 422, res.text


# ── 5: submitted report retains the manually entered code ──────────────────

def test_submitted_report_retains_manual_project_code(client, setup_author, pm_header):
    a = setup_author(project_code=None)
    created = _create(
        client, a["header"],
        [_task(a["project"].id, manual_project_code="TAG-EST-2026")],
    ).json()
    res = client.post(f"{BASE}/{created['id']}/submit", headers=a["header"])
    assert res.status_code == 200, res.text
    assert res.json()["tasks"][0]["project_code"] == "TAG-EST-2026"

    fetched = client.get(f"{BASE}/{created['id']}", headers=a["header"]).json()
    assert fetched["tasks"][0]["project_code"] == "TAG-EST-2026"


# ── 7: never written back to the Project Master ─────────────────────────────

def test_manual_project_code_never_updates_project_master(client, setup_author, db):
    a = setup_author(project_code=None)
    res = _create(
        client, a["header"],
        [_task(a["project"].id, manual_project_code="TAG-EST-2026")],
    )
    assert res.status_code == 201, res.text

    with SessionLocal() as fresh:
        project = fresh.get(Project, a["project"].id)
        assert project.code is None


# ── 8: historical reports without a manual entry keep loading ──────────────

def test_historical_report_without_manual_code_still_loads(
    client, setup_author, db
):
    """A row saved before this feature existed carries no manual_project_code
    input at all (there is no new column — project_code is the pre-existing
    migration-0017 snapshot) and must keep reading back exactly as it always
    did for a normal, coded project."""
    a = setup_author(project_code="4391-GC21107300")
    created = _create(client, a["header"], [_task(a["project"].id)]).json()

    fetched = client.get(f"{BASE}/{created['id']}", headers=a["header"])
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["tasks"][0]["project_code"] == "4391-GC21107300"


# ── editing an existing draft ───────────────────────────────────────────────

def test_editing_draft_can_change_the_manual_project_code(client, setup_author):
    a = setup_author(project_code=None)
    created = _create(
        client, a["header"],
        [_task(a["project"].id, manual_project_code="TAG-EST-DRAFT")],
    ).json()

    res = client.patch(
        f"{BASE}/{created['id']}", headers=a["header"],
        json={"tasks": [_task(a["project"].id, manual_project_code="TAG-EST-FINAL")]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["tasks"][0]["project_code"] == "TAG-EST-FINAL"


def test_editing_draft_without_manual_code_is_rejected(client, setup_author):
    a = setup_author(project_code=None)
    created = _create(
        client, a["header"],
        [_task(a["project"].id, manual_project_code="TAG-EST-DRAFT")],
    ).json()

    res = client.patch(
        f"{BASE}/{created['id']}", headers=a["header"],
        json={"tasks": [_task(a["project"].id)]},
    )
    assert res.status_code == 422, res.text


# ── 9: export shows the effective code ──────────────────────────────────────

def test_export_rows_show_the_effective_project_code(client, setup_author, pm_header):
    a = setup_author(project_code=None)
    created = _create(
        client, a["header"],
        [_task(a["project"].id, manual_project_code="TAG-EST-2026")],
    ).json()
    client.post(f"{BASE}/{created['id']}/submit", headers=a["header"])

    body = client.get(
        "/api/v1/reports-export/activity-rows", headers=pm_header
    ).json()
    assert body["rows"], "expected the submitted report's row in the export"
    activities = body["rows"][0]["activities"]
    assert activities and activities[0]["project_code"] == "TAG-EST-2026"


# ── activity-request approval on a no-code project is unaffected ───────────

def test_validate_tasks_require_project_code_false_preserves_old_behaviour(
    setup_author, db,
):
    """`_create_task_from_request` (activity_requests/service.py — the PM
    activity-approval path, which never collects an employee-entered project
    code) calls `_validate_tasks(..., require_project_code=False)`. On a
    no-code project this must NOT raise the new 422 — it keeps the exact
    pre-feature behaviour of that untouched approval flow: the snapshot is
    simply whatever the project has (None here), never an error."""
    from types import SimpleNamespace

    from app.modules.work_reports.service import _validate_tasks

    a = setup_author(project_code=None)
    row = SimpleNamespace(
        project_id=a["project"].id,
        description="",
        minutes_spent=None,
        task_minutes_spent=None,
        activity_type=None,
        tags_count=0, docs_count=0, bom_count=0, spares_count=0,
        pages_count=0, records_count=0,
        sub_activity_id=None,
        is_completed=False,
        maintenance_plant_id=None,
    )
    _total, snapshots = _validate_tasks(
        db, a["emp"].id, [row], require_project_code=False,
    )
    assert snapshots[0]["project_code"] is None
