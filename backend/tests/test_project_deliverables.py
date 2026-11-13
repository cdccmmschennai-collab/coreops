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
import uuid
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

def test_deadline_change_reason_is_optional_and_is_logged(client, login, world, db):
    h = login("head@x.com")
    url = f"/api/v1/projects/{world['p1'].id}/deliverables/{world['d1'].id}"
    first = (TODAY + timedelta(days=7)).isoformat()
    second = (TODAY + timedelta(days=8)).isoformat()

    assert client.patch(url, headers=h, json={"target_date": first}).status_code == 200
    ok = client.patch(url, headers=h, json={"target_date": second, "reason": "Rescoped"})
    assert ok.status_code == 200, ok.text

    changes = db.query(DeliverableChange).filter_by(deliverable_id=world["d1"].id).all()
    assert sorted((c.new_value, c.reason) for c in changes) == [
        (first, ""),
        (second, "Rescoped"),
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
                                 status=PLANNED, target_date=TODAY - timedelta(days=1),
                                 owner_employee_id=world["member"].id)
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


def test_status_changes_need_no_reason(client, login, world):
    """Completing and reverting both work without a reason (it is optional)."""
    h = login("pm@x.com")
    url = f"/api/v1/projects/{world['p1'].id}/deliverables/{world['d1'].id}"
    assert client.patch(url, headers=h, json={"status": "completed"}).status_code == 200
    back = client.patch(url, headers=h, json={"status": "planned"})
    assert back.status_code == 200
    assert back.json()["deadline_state"] == "due_soon"


def test_completion_stamps_actual_submission_and_reversal_clears_it(client, login, world):
    from app.modules.project_deliverables.deadline import business_today

    h = login("pm@x.com")
    url = f"/api/v1/projects/{world['p1'].id}/deliverables/{world['d1'].id}"
    done = client.patch(url, headers=h, json={"status": "completed"}).json()
    assert done["completion_date"] == business_today().isoformat()
    back = client.patch(url, headers=h, json={"status": "planned", "reason": "Redo"}).json()
    assert back["completion_date"] is None
    given = client.patch(
        url, headers=h, json={"status": "completed", "completion_date": "2026-01-05"}
    ).json()
    assert given["completion_date"] == "2026-01-05"


def test_existing_response_fields_are_unchanged(client, login, world):
    legacy = {"id", "project_id", "project_name", "project_code", "name", "description",
              "planned_start_date", "target_date", "owner_employee_id", "owner_name",
              "status", "completion_date", "created_at", "updated_at"}
    added = {"can_manage", "days_remaining", "deadline_state", "owner_role"}
    row = client.get("/api/v1/deliverables", headers=login("pm@x.com")).json()[0]
    assert set(row) == legacy | added


def test_deadline_state_is_not_a_stored_column():
    cols = set(ProjectDeliverable.__table__.columns.keys())
    assert not cols & {"days_remaining", "deadline_state", "can_manage", "owner_role"}
    assert set(DeliverableStatus) == {PLANNED, COMPLETED}


# ======================================================================
# Assignee (owner_employee_id)
# ======================================================================

def _assignees_url(world, key="p1"):
    return f"/api/v1/projects/{world[key].id}/deliverables/assignees"


def test_assignee_options_are_head_first_then_members(client, login, world):
    res = client.get(_assignees_url(world), headers=login("pm@x.com"))
    assert res.status_code == 200, res.text
    rows = res.json()
    assert rows[0] == {"employee_id": str(world["head"].id), "name": "Test User",
                       "role": "project_head"}
    assert {r["employee_id"] for r in rows[1:]} == {
        str(world[k].id) for k in ("member", "lead", "qc")
    }
    assert all(r["role"] == "employee" for r in rows[1:])
    # Head of P1 sees the same options; never another project's people.
    head_rows = client.get(_assignees_url(world), headers=login("head@x.com")).json()
    assert head_rows == rows
    assert str(world["head2"].id) not in {r["employee_id"] for r in rows}


@pytest.mark.parametrize("who", ["member", "lead", "outsider", "head2"])
def test_assignee_options_are_manager_only(client, login, world, who):
    assert client.get(_assignees_url(world), headers=login(f"{who}@x.com")).status_code == 403


def test_assignee_options_skip_exited_employees(client, login, world, db):
    from app.modules.employees.models import EmployeeStatus
    world["qc"].status = EmployeeStatus.exited
    db.commit()
    ids = {r["employee_id"] for r in
           client.get(_assignees_url(world), headers=login("pm@x.com")).json()}
    assert str(world["qc"].id) not in ids


def test_employee_assignment_shows_in_list_and_detail(client, login, world):
    h = login("head@x.com")
    res = client.post(f"/api/v1/projects/{world['p1'].id}/deliverables", headers=h,
                      json={"name": "ASSET REGISTER",
                            "owner_employee_id": str(world["member"].id)})
    assert res.status_code == 201, res.text
    assert res.json()["owner_name"] == "Test User"
    assert res.json()["owner_role"] == "employee"
    did = res.json()["id"]

    row = next(r for r in client.get("/api/v1/deliverables", headers=h).json()
               if r["id"] == did)
    detail = client.get(f"/api/v1/deliverables/{did}", headers=h).json()
    for out in (row, detail):
        assert out["owner_employee_id"] == str(world["member"].id)
        assert (out["owner_name"], out["owner_role"]) == ("Test User", "employee")


def test_project_head_assignment_and_reassign_and_unassign(client, login, world):
    h = login("pm@x.com")
    base = f"/api/v1/projects/{world['p1'].id}/deliverables"
    url = f"{base}/{world['d1'].id}"

    to_head = client.patch(url, headers=h, json={"owner_employee_id": str(world["head"].id)})
    assert to_head.status_code == 200, to_head.text
    assert to_head.json()["owner_role"] == "project_head"

    to_lead = client.patch(url, headers=h, json={"owner_employee_id": str(world["lead"].id)})
    assert to_lead.json()["owner_role"] == "employee"
    detail = client.get(f"/api/v1/deliverables/{world['d1'].id}", headers=h).json()
    assert detail["owner_employee_id"] == str(world["lead"].id)

    cleared = client.patch(url, headers=h, json={"owner_employee_id": None})
    assert cleared.status_code == 200
    assert (cleared.json()["owner_employee_id"], cleared.json()["owner_name"],
            cleared.json()["owner_role"]) == (None, None, None)


def test_unassigned_deliverable_has_no_assignee(client, login, world):
    row = client.get(f"/api/v1/deliverables/{world['d1'].id}",
                     headers=login("member@x.com")).json()
    assert (row["owner_employee_id"], row["owner_name"], row["owner_role"]) == (None, None, None)


@pytest.mark.parametrize("who", ["outsider", "head2"])
def test_cannot_assign_someone_outside_the_project(client, login, world, who, db):
    import uuid as _uuid
    h = login("pm@x.com")
    base = f"/api/v1/projects/{world['p1'].id}/deliverables"
    bad = str(world[who].id)
    assert client.post(base, headers=h,
                       json={"name": "X", "owner_employee_id": bad}).status_code == 422
    assert client.patch(f"{base}/{world['d1'].id}", headers=h,
                        json={"owner_employee_id": bad}).status_code == 422
    assert client.patch(f"{base}/{world['d1'].id}", headers=h,
                        json={"owner_employee_id": str(_uuid.uuid4())}).status_code == 422
    db.expire_all()
    assert db.get(ProjectDeliverable, world["d1"].id).owner_employee_id is None


def test_non_manager_cannot_change_assignee(client, login, world, db):
    res = client.patch(f"/api/v1/projects/{world['p1'].id}/deliverables/{world['d1'].id}",
                       headers=login("member@x.com"),
                       json={"owner_employee_id": str(world["member"].id)})
    assert res.status_code == 403
    db.expire_all()
    assert db.get(ProjectDeliverable, world["d1"].id).owner_employee_id is None


def test_unchanged_stale_assignee_does_not_block_other_edits(client, login, world, db):
    # Assignee later left the project: re-sending the same id with an
    # unrelated edit must still succeed (only a CHANGE is validated).
    world["d1"].owner_employee_id = world["outsider"].id
    db.commit()
    res = client.patch(f"/api/v1/projects/{world['p1'].id}/deliverables/{world['d1'].id}",
                       headers=login("pm@x.com"),
                       json={"name": "FMTL v2", "owner_employee_id": str(world["outsider"].id)})
    assert res.status_code == 200, res.text
    assert res.json()["owner_role"] == "employee"


# ======================================================================
# Notifications go to the Assignee + project Head only (never all members)
# ======================================================================

def _notified(db, deliverable_id, type_):
    """{user email: count} of notifications of `type_` for this deliverable."""
    from app.modules.notifications.models import Notification
    from app.modules.users.models import User as _User
    db.expire_all()
    rows = db.query(Notification).filter(
        Notification.entity_id == deliverable_id, Notification.type == type_
    ).all()
    out = {}
    for n in rows:
        email = db.get(_User, n.user_id).email
        out[email] = out.get(email, 0) + 1
    return out


def test_planned_notifies_assignee_and_head_not_other_members(client, login, world, db):
    res = client.post(f"/api/v1/projects/{world['p1'].id}/deliverables",
                      headers=login("pm@x.com"),
                      json={"name": "ASSET REGISTER",
                            "owner_employee_id": str(world["member"].id)})
    assert res.status_code == 201, res.text
    got = _notified(db, uuid.UUID(res.json()["id"]), "deliverable_planned")
    assert got == {"member@x.com": 1, "head@x.com": 1}     # lead / qc get nothing


def test_unassigned_deliverable_notifies_head_only(client, login, world, db):
    res = client.post(f"/api/v1/projects/{world['p1'].id}/deliverables",
                      headers=login("pm@x.com"), json={"name": "NO OWNER"})
    assert _notified(db, uuid.UUID(res.json()["id"]), "deliverable_planned") == {"head@x.com": 1}


def test_assignee_who_is_the_head_is_notified_once(client, login, world, db):
    h = login("pm@x.com")
    base = f"/api/v1/projects/{world['p1'].id}/deliverables"
    res = client.post(base, headers=h, json={"name": "HEAD OWNED",
                                             "owner_employee_id": str(world["head"].id)})
    did = res.json()["id"]
    assert _notified(db, uuid.UUID(did), "deliverable_planned") == {"head@x.com": 1}
    client.patch(f"{base}/{did}", headers=h, json={"status": "completed"})
    assert _notified(db, uuid.UUID(did), "deliverable_completed") == {"head@x.com": 1}


def test_assigning_notifies_new_assignee_and_head(client, login, world, db):
    h = login("pm@x.com")
    url = f"/api/v1/projects/{world['p1'].id}/deliverables/{world['d1'].id}"
    client.patch(url, headers=h, json={"owner_employee_id": str(world["lead"].id)})
    assert _notified(db, world["d1"].id, "deliverable_assigned") == {
        "lead@x.com": 1, "head@x.com": 1}
    # Re-sending the same Assignee is not a new assignment.
    client.patch(url, headers=h, json={"owner_employee_id": str(world["lead"].id), "name": "FMTL"})
    assert _notified(db, world["d1"].id, "deliverable_assigned") == {
        "lead@x.com": 1, "head@x.com": 1}
    # Clearing the Assignee sends no assignment notification.
    client.patch(url, headers=h, json={"owner_employee_id": None})
    assert _notified(db, world["d1"].id, "deliverable_assigned") == {
        "lead@x.com": 1, "head@x.com": 1}


def test_date_change_and_completion_go_to_assignee_and_head_only(client, login, world, db):
    h = login("pm@x.com")
    url = f"/api/v1/projects/{world['p1'].id}/deliverables/{world['d1'].id}"
    client.patch(url, headers=h, json={"owner_employee_id": str(world["qc"].id)})
    client.patch(url, headers=h, json={"target_date": (TODAY + timedelta(days=8)).isoformat()})
    client.patch(url, headers=h, json={"status": "completed"})
    for type_ in ("deliverable_date_updated", "deliverable_completed"):
        assert _notified(db, world["d1"].id, type_) == {"qc@x.com": 1, "head@x.com": 1}, type_


# ======================================================================
# Deliverable impact (leave review) - Assignee only
# ======================================================================

def _impact_names(client, login, leave_id):
    res = client.post("/api/v1/leave-requests/deliverable-impact", headers=login("pm@x.com"),
                      json={"leave_request_ids": [str(leave_id)]})
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    return sorted(c["deliverable_name"] for i in items for c in i["conflicts"])


def test_impact_only_for_the_assignee_on_leave(client, login, world, make_leave_request, db):
    world["d1"].owner_employee_id = world["member"].id     # FMTL, due in 3 days
    db.add(ProjectDeliverable(project_id=world["p1"].id, name="UNASSIGNED DOC",
                              status=PLANNED, target_date=TODAY + timedelta(days=3)))
    db.commit()
    day = TODAY + timedelta(days=2)
    member_leave = make_leave_request(employee_id=world["member"].id, start_date=day, end_date=day)
    lead_leave = make_leave_request(employee_id=world["lead"].id, start_date=day, end_date=day)
    head_leave = make_leave_request(employee_id=world["head"].id, start_date=day, end_date=day)

    assert _impact_names(client, login, member_leave.id) == ["FMTL"]
    # Same project, but not the Assignee: no impact (nor for unassigned ones).
    assert _impact_names(client, login, lead_leave.id) == []
    assert _impact_names(client, login, head_leave.id) == []