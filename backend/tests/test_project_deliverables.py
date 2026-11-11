"""Project deliverables - Phase 2 of the submission-deadline tracker.

Pins:
  * the derived deadline ladder (ADR-003 Amendment 2) and its IST "today";
  * manage = PM (any project) or the assigned project Head (own projects only);
    a team-lead project role grants nothing extra;
  * view = PM / Head / project member; soft-deleted projects are invisible;
  * the stored status stays planned/completed, so leave Deliverable Impact
    still sees an overdue deliverable.

    docker exec wms-backend-1 pytest tests/test_project_deliverables.py
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.modules.audit.models import AuditLog
from app.modules.project_deliverables import deadline
from app.modules.project_deliverables.models import (
    DeliverableChange,
    DeliverableStatus,
    ProjectDeliverable,
)
from app.modules.projects.models import ProjectMemberRole
from app.modules.users.models import UserRole

TODAY = deadline.business_today()
PLANNED = DeliverableStatus.planned
COMPLETED = DeliverableStatus.completed


# ======================================================================
# Pure deadline ladder
# ======================================================================

@pytest.mark.parametrize(
    "offset, state",
    [
        (-10, "overdue"),
        (-1, "overdue"),
        (0, "due_today"),
        (1, "urgent"),
        (2, "due_soon"),
        (5, "due_soon"),
        (6, "on_track"),
        (30, "on_track"),
    ],
)
def test_deadline_ladder(offset, state):
    target = TODAY + timedelta(days=offset)
    assert deadline.deadline_state(target, PLANNED, TODAY) == state
    assert deadline.days_remaining(target, PLANNED, TODAY) == offset


def test_reminder_window_is_five_days():
    assert deadline.REMINDER_WINDOW_DAYS == 5


def test_no_deadline():
    assert deadline.deadline_state(None, PLANNED, TODAY) == "no_deadline"
    assert deadline.days_remaining(None, PLANNED, TODAY) is None


@pytest.mark.parametrize("offset", [-3, 0, 4, None])
def test_completed_wins_over_any_date(offset):
    target = None if offset is None else TODAY + timedelta(days=offset)
    assert deadline.deadline_state(target, COMPLETED, TODAY) == "completed"
    assert deadline.days_remaining(target, COMPLETED, TODAY) is None


def test_business_today_is_ist_not_utc(monkeypatch):
    """01:30 IST on 12 Nov is still 11 Nov in UTC - the business date must be
    the 12th."""
    utc_instant = datetime(2026, 11, 11, 20, 0, tzinfo=timezone.utc)

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return utc_instant.astimezone(tz) if tz else utc_instant

    monkeypatch.setattr(deadline, "datetime", _Frozen)
    assert deadline.business_today().isoformat() == "2026-11-12"


# ======================================================================
# API fixtures
# ======================================================================

@pytest.fixture()
def world(make_user, make_employee, make_project, make_project_member, db):
    """
    P1  head = head (no explicit member row - Head alone must be enough),
        members: member (contributor), lead (team_lead), qc (qc)
    P2  head = head2 (another Head's project)
    P3  soft-deleted project `member` belongs to
    `outsider` belongs to nothing.
    """
    pm_u = make_user("pm@x.com", role=UserRole.project_manager)
    people, users = {}, {"pm": pm_u}
    for key, code in (("head", "HD1"), ("head2", "HD2"), ("member", "MB1"),
                      ("lead", "TL1"), ("qc", "QC1"), ("outsider", "OT1")):
        users[key] = make_user(f"{key}@x.com", role=UserRole.employee)
        people[key] = make_employee(employee_code=code, user_id=users[key].id)

    p1 = make_project(code="P1", name="Project One", head_employee_id=people["head"].id)
    p2 = make_project(code="P2", name="Project Two", head_employee_id=people["head2"].id)
    p3 = make_project(code="P3", name="Deleted Project")
    make_project_member(project_id=p1.id, employee_id=people["member"].id)
    make_project_member(project_id=p1.id, employee_id=people["lead"].id,
                        role=ProjectMemberRole.team_lead)
    make_project_member(project_id=p1.id, employee_id=people["qc"].id,
                        role=ProjectMemberRole.qc)
    make_project_member(project_id=p3.id, employee_id=people["member"].id)

    d1 = ProjectDeliverable(project_id=p1.id, name="FMTL", status=PLANNED,
                            target_date=TODAY + timedelta(days=3))
    d2 = ProjectDeliverable(project_id=p2.id, name="MTL", status=PLANNED,
                            target_date=TODAY)
    d3 = ProjectDeliverable(project_id=p3.id, name="DOC IDB", status=PLANNED,
                            target_date=TODAY)
    db.add_all([d1, d2, d3])
    p3.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"pm": pm_u, **people, "users": users, "p1": p1, "p2": p2, "p3": p3,
            "d1": d1, "d2": d2, "d3": d3}


ALL_LOGINS = ["pm", "head", "head2", "member", "lead", "qc", "outsider"]


def _names(res):
    assert res.status_code == 200, res.text
    return sorted(r["name"] for r in res.json())


# ======================================================================
# Visibility
# ======================================================================

def test_pm_sees_every_live_project_and_can_manage_all(client, login, world):
    res = client.get("/api/v1/deliverables", headers=login("pm@x.com"))
    assert _names(res) == ["FMTL", "MTL"]          # deleted P3 excluded
    assert all(r["can_manage"] for r in res.json())


def test_head_sees_and_manages_own_project_only(client, login, world):
    res = client.get("/api/v1/deliverables", headers=login("head@x.com"))
    assert _names(res) == ["FMTL"]
    assert res.json()[0]["can_manage"] is True


def test_member_sees_own_project_read_only_and_not_deleted(client, login, world):
    res = client.get("/api/v1/deliverables", headers=login("member@x.com"))
    assert _names(res) == ["FMTL"]                 # P3 membership ignored: deleted
    assert res.json()[0]["can_manage"] is False


def test_team_lead_is_read_only(client, login, world):
    res = client.get("/api/v1/deliverables", headers=login("lead@x.com"))
    assert _names(res) == ["FMTL"]
    assert res.json()[0]["can_manage"] is False


def test_outsider_sees_nothing(client, login, world):
    h = login("outsider@x.com")
    assert _names(client.get("/api/v1/deliverables", headers=h)) == []
    assert client.get(f"/api/v1/deliverables/{world['d1'].id}", headers=h).status_code == 403
    assert client.get(f"/api/v1/deliverables/{world['d1'].id}/changes",
                      headers=h).status_code == 403
    assert client.get(f"/api/v1/projects/{world['p1'].id}/deliverables",
                      headers=h).status_code == 403


def test_head_without_member_row_can_read_detail_and_history(client, login, world):
    h = login("head@x.com")
    detail = client.get(f"/api/v1/deliverables/{world['d1'].id}", headers=h)
    assert detail.status_code == 200, detail.text
    assert detail.json()["can_manage"] is True
    assert client.get(f"/api/v1/deliverables/{world['d1'].id}/changes",
                      headers=h).status_code == 200


def test_per_project_list_carries_can_manage(client, login, world):
    url = f"/api/v1/projects/{world['p1'].id}/deliverables"
    assert client.get(url, headers=login("head@x.com")).json()[0]["can_manage"] is True
    assert client.get(url, headers=login("member@x.com")).json()[0]["can_manage"] is False


def test_deleted_project_deliverable_is_not_found_even_for_pm(client, login, world):
    res = client.get(f"/api/v1/deliverables/{world['d3'].id}", headers=login("pm@x.com"))
    assert res.status_code == 404


# ======================================================================
# Manage permissions
# ======================================================================

def test_head_can_create_edit_and_delete_on_own_project(client, login, world, db):
    h = login("head@x.com")
    base = f"/api/v1/projects/{world['p1'].id}/deliverables"

    created = client.post(base, headers=h, json={
        "name": "PM IDB", "target_date": (TODAY + timedelta(days=10)).isoformat(),
    })
    assert created.status_code == 201, created.text
    did = created.json()["id"]
    assert created.json()["can_manage"] is True

    moved = client.patch(f"{base}/{did}", headers=h, json={
        "target_date": (TODAY + timedelta(days=4)).isoformat(),
        "reason": "Client moved the submission",
    })
    assert moved.status_code == 200, moved.text
    assert moved.json()["deadline_state"] == "due_soon"

    done = client.patch(f"{base}/{did}", headers=h, json={"status": "completed"})
    assert done.status_code == 200, done.text
    assert done.json()["deadline_state"] == "completed"

    assert client.delete(f"{base}/{did}", headers=h).status_code == 204


def test_head_cannot_manage_another_project(client, login, world):
    h = login("head@x.com")
    base = f"/api/v1/projects/{world['p2'].id}/deliverables"
    assert client.post(base, headers=h, json={"name": "X"}).status_code == 403
    assert client.patch(f"{base}/{world['d2'].id}", headers=h,
                        json={"name": "Y"}).status_code == 403
    assert client.delete(f"{base}/{world['d2'].id}", headers=h).status_code == 403


@pytest.mark.parametrize("who", ["member", "lead", "qc", "outsider", "head2"])
def test_non_managers_cannot_create_edit_or_delete(client, login, world, who, db):
    h = login(f"{who}@x.com")
    base = f"/api/v1/projects/{world['p1'].id}/deliverables"
    did = world["d1"].id
    assert client.post(base, headers=h, json={"name": "X"}).status_code == 403
    assert client.patch(f"{base}/{did}", headers=h, json={
        "target_date": (TODAY + timedelta(days=9)).isoformat(), "reason": "nope",
    }).status_code == 403
    assert client.patch(f"{base}/{did}", headers=h,
                        json={"status": "completed"}).status_code == 403
    assert client.delete(f"{base}/{did}", headers=h).status_code == 403

    db.expire_all()
    row = db.get(ProjectDeliverable, did)
    assert row.status == PLANNED and row.target_date == TODAY + timedelta(days=3)


def test_pm_can_manage_any_project(client, login, world):
    h = login("pm@x.com")
    res = client.post(f"/api/v1/projects/{world['p2'].id}/deliverables", headers=h,
                      json={"name": "DOC IDB"})
    assert res.status_code == 201, res.text
    assert res.json()["deadline_state"] == "no_deadline"
    assert res.json()["days_remaining"] is None


# ======================================================================
# History and reason rule preserved
# ======================================================================

def test_deadline_change_still_needs_reason_and_is_logged(client, login, world, db):
    h = login("head@x.com")
    url = f"/api/v1/projects/{world['p1'].id}/deliverables/{world['d1'].id}"
    new_date = (TODAY + timedelta(days=8)).isoformat()

    assert client.patch(url, headers=h, json={"target_date": new_date}).status_code == 422

    ok = client.patch(url, headers=h, json={"target_date": new_date, "reason": "Rescoped"})
    assert ok.status_code == 200, ok.text

    changes = db.query(DeliverableChange).filter_by(deliverable_id=world["d1"].id).all()
    assert [(c.field, c.new_value, c.reason) for c in changes] == [
        ("due_date", new_date, "Rescoped")
    ]


# ======================================================================
# Derived state over the API + storage untouched
# ======================================================================

def test_response_carries_derived_deadline_fields(client, login, world):
    res = client.get("/api/v1/deliverables", headers=login("pm@x.com")).json()
    by_name = {r["name"]: r for r in res}
    assert (by_name["FMTL"]["days_remaining"], by_name["FMTL"]["deadline_state"]) == (3, "due_soon")
    assert (by_name["MTL"]["days_remaining"], by_name["MTL"]["deadline_state"]) == (0, "due_today")


def test_overdue_is_not_persisted_and_still_counts_for_leave_impact(
    client, login, world, make_leave_request, db
):
    """An overdue deliverable keeps stored status 'planned', so the leave
    review's +/-2 day Deliverable Impact still flags it."""
    overdue = ProjectDeliverable(project_id=world["p1"].id, name="MTL rev B",
                                 status=PLANNED, target_date=TODAY - timedelta(days=1))
    db.add(overdue)
    db.commit()

    row = client.get(f"/api/v1/deliverables/{overdue.id}", headers=login("pm@x.com")).json()
    assert row["deadline_state"] == "overdue" and row["days_remaining"] == -1
    assert row["status"] == "planned"

    leave = make_leave_request(employee_id=world["member"].id,
                               start_date=TODAY, end_date=TODAY)
    impact = client.post("/api/v1/leave-requests/deliverable-impact",
                         headers=login("pm@x.com"),
                         json={"leave_request_ids": [str(leave.id)]})
    assert impact.status_code == 200, impact.text
    names = {c["deliverable_name"] for c in impact.json()["items"][0]["conflicts"]}
    assert "MTL rev B" in names


# ======================================================================
# Phase 2 verification - consistency, identity, compatibility
# ======================================================================

def test_head2_sees_only_own_project(client, login, world):
    res = client.get("/api/v1/deliverables", headers=login("head2@x.com"))
    assert _names(res) == ["MTL"]
    assert res.json()[0]["can_manage"] is True


def test_qc_sees_project_read_only(client, login, world):
    res = client.get("/api/v1/deliverables", headers=login("qc@x.com"))
    assert _names(res) == ["FMTL"]
    assert res.json()[0]["can_manage"] is False


@pytest.mark.parametrize("who", ALL_LOGINS)
def test_can_manage_flag_matches_backend_enforcement(client, login, world, who):
    """For every row a caller can see, `can_manage` predicts exactly whether an
    edit is accepted (200) or refused (403)."""
    h = login(f"{who}@x.com")
    rows = client.get("/api/v1/deliverables", headers=h).json()
    for r in rows:
        res = client.patch(f"/api/v1/projects/{r['project_id']}/deliverables/{r['id']}",
                           headers=h, json={"description": f"edited by {who}"})
        assert res.status_code == (200 if r["can_manage"] else 403), (who, r["name"], res.text)
        detail = client.get(f"/api/v1/deliverables/{r['id']}", headers=h).json()
        assert detail["can_manage"] == r["can_manage"]


def test_head_changes_are_recorded_with_head_identity(client, login, world, db):
    h = login("head@x.com")
    head_user = world["users"]["head"]
    url = f"/api/v1/projects/{world['p1'].id}/deliverables/{world['d1'].id}"
    new_date = (TODAY + timedelta(days=12)).isoformat()

    assert client.patch(url, headers=h, json={"target_date": new_date,
                                               "reason": "Client asked"}).status_code == 200
    assert client.patch(url, headers=h, json={"status": "completed"}).status_code == 200

    changes = client.get(f"/api/v1/deliverables/{world['d1'].id}/changes", headers=h).json()
    assert {(c["field"], c["new_value"]) for c in changes} == {
        ("due_date", new_date), ("status", "completed"),
    }
    assert {c["changed_by"] for c in changes} == {str(head_user.id)}
    assert {c["changed_by_name"] for c in changes} == {"head@x.com"}

    audits = db.query(AuditLog).filter_by(entity_id=world["d1"].id).all()
    assert len(audits) == 2
    assert {a.actor_user_id for a in audits} == {head_user.id}
    assert {a.action for a in audits} == {"deliverable.field.change"}


def test_status_reversal_needs_reason_forward_completion_does_not(client, login, world):
    """Existing (0045) rule, unchanged by Phase 2: completing needs no reason
    (logged with a system reason); reverting completed -> planned does."""
    h = login("pm@x.com")
    url = f"/api/v1/projects/{world['p1'].id}/deliverables/{world['d1'].id}"
    assert client.patch(url, headers=h, json={"status": "completed"}).status_code == 200
    assert client.patch(url, headers=h, json={"status": "planned"}).status_code == 422
    back = client.patch(url, headers=h, json={"status": "planned", "reason": "Rejected by client"})
    assert back.status_code == 200
    assert back.json()["deadline_state"] == "due_soon"


def test_existing_response_fields_are_unchanged(client, login, world):
    legacy = {"id", "project_id", "project_name", "project_code", "name", "description",
              "planned_start_date", "target_date", "owner_employee_id", "owner_name",
              "status", "completion_date", "created_at", "updated_at"}
    added = {"can_manage", "days_remaining", "deadline_state"}
    row = client.get("/api/v1/deliverables", headers=login("pm@x.com")).json()[0]
    assert set(row) == legacy | added


def test_deadline_state_is_not_a_stored_column():
    cols = set(ProjectDeliverable.__table__.columns.keys())
    assert not cols & {"days_remaining", "deadline_state", "can_manage"}
    assert set(DeliverableStatus) == {PLANNED, COMPLETED}
