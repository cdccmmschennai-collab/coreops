"""Rework Activity Approval - Phase 2: raising requests at submit (migration 0091).

Covers spec tests 1, 2, 3, 5, 13, 18, 19 plus routing/email. Review, correction
and outstanding monitoring are later phases.
"""
from datetime import date

import pytest
from sqlalchemy import select

from app.modules.notifications.models import Notification
from app.modules.projects.models import ProjectStatus
from app.modules.rework_approvals import email as rework_email
from app.modules.rework_approvals.models import ReworkApprovalRequest
from app.modules.users.models import UserRole

AM = "/api/v1/activity-master"
WR = "/api/v1/work-reports"
TODAY = date.today().isoformat()


def _activity(client, h, name):
    res = client.post(f"{AM}/activities", json={"name": name}, headers=h)
    assert res.status_code == 201, res.text
    return res.json()


def _sub(client, h, activity_id, name, approval=False):
    res = client.post(
        f"{AM}/activities/{activity_id}/sub-activities", json={"name": name}, headers=h
    )
    assert res.status_code == 201, res.text
    sub = res.json()
    if approval:
        r = client.put(
            f"{AM}/sub-activities/{sub['id']}/approval",
            json={"requires_pm_approval": True},
            headers=h,
        )
        assert r.status_code == 200, r.text
    return sub


def _task(project_id, sub_id, remark="work"):
    return {"project_id": str(project_id), "description": remark, "sub_activity_id": str(sub_id)}


@pytest.fixture()
def setup(client, make_user, make_employee, make_project, make_project_member, login):
    """A PM (with a work email), an employee reporting to them on one project,
    one normal sub-activity and one configured rework sub-activity."""
    pm_user = make_user("pm@x.com", role=UserRole.project_manager)
    make_employee(
        employee_code="PM1", first_name="Priya", last_name="PM",
        user_id=pm_user.id, work_email="pm.work@x.com",
    )
    pm = login("pm@x.com")
    emp_user = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(
        employee_code="CDC031", first_name="ABIRAMI", last_name="S",
        user_id=emp_user.id, reporting_pm_id=pm_user.id,
    )
    project = make_project(code="P1", name="Project A", status=ProjectStatus.active)
    make_project_member(project_id=project.id, employee_id=emp.id)
    act = _activity(client, pm, "INSTRUMENT ENGINEERING")
    normal = _sub(client, pm, act["id"], "Instrument Design")
    rework = _sub(client, pm, act["id"], "Instrument Rework", approval=True)
    return {
        "pm": pm, "pm_user": pm_user, "emp": emp, "header": login("emp@x.com"),
        "project": project, "normal": normal, "rework": rework,
    }


@pytest.fixture()
def sent(monkeypatch):
    """Captures queued emails instead of touching the broker."""
    out = []

    class _Result:
        queued, reason, task_id = True, None, "t"

    def fake_enqueue(**kw):
        out.append(kw)
        return _Result()

    monkeypatch.setattr(rework_email, "enqueue_email", fake_enqueue)
    return out


def _create(client, s, tasks, remarks=None):
    body = {"report_date": TODAY, "day_status": "work_at_office", "tasks": tasks}
    if remarks is not None:
        body["remarks"] = remarks
    res = client.post(WR, headers=s["header"], json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _submit(client, s, report_id):
    return client.post(f"{WR}/{report_id}/submit", headers=s["header"])


def _requests(db):
    db.expire_all()
    return list(db.execute(select(ReworkApprovalRequest)).scalars())


def _row(report, sub_id):
    return next(t for t in report["tasks"] if t["sub_activity_id"] == sub_id)


# TEST 1 / 19: normal activities behave exactly as before.
def test_normal_report_raises_nothing(client, db, setup, sent):
    s = setup
    r = _create(client, s, [_task(s["project"].id, s["normal"]["id"])])
    res = _submit(client, s, r["id"])
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "submitted"
    assert _row(res.json(), s["normal"]["id"])["rework_approval_status"] is None
    assert _requests(db) == []
    assert sent == []


# TEST 2: a draft never raises a request or sends anything.
def test_draft_raises_nothing(client, db, setup, sent):
    s = setup
    r = _create(client, s, [_task(s["project"].id, s["rework"]["id"])])
    assert r["status"] == "draft"
    assert _row(r, s["rework"]["id"])["rework_approval_status"] is None
    assert _requests(db) == []
    assert sent == []


# TEST 3 + routing + email content.
def test_submit_raises_request_and_notifies_reporting_pm(client, db, setup, sent):
    s = setup
    r = _create(client, s, [_task(s["project"].id, s["rework"]["id"], remark="Fix loop drawings")])
    res = _submit(client, s, r["id"])
    assert res.status_code == 200, res.text
    row = _row(res.json(), s["rework"]["id"])
    assert row["rework_approval_status"] == "pending"

    [req] = _requests(db)
    assert req.status == "pending" and req.cycle_no == 1
    assert req.day_part == "full_day"
    assert req.activity_name == "INSTRUMENT ENGINEERING"
    assert req.sub_activity_name == "Instrument Rework"
    assert req.employee_remarks == "Fix loop drawings"
    assert str(req.id) == row["rework_request_id"]

    bell = db.execute(
        select(Notification).where(Notification.type == "rework_approval_requested")
    ).scalars().all()
    assert [n.user_id for n in bell] == [s["pm_user"].id]
    assert bell[0].target_url == f"/activity-requests/rework/{req.id}"

    [mail] = sent
    assert mail["to"] == "pm.work@x.com"
    assert "Rework Approval Request" in mail["subject"]
    body = mail["text_body"]
    for expected in (
        "CDC031 - ABIRAMI S", "INSTRUMENT ENGINEERING", "Instrument Rework",
        "Day Part: Full Day", "Fix loop drawings",
    ):
        assert expected in body
    assert "hour" not in body.lower()


# TEST 5: one normal + one rework -> only the rework row is in review.
def test_mixed_report_only_rework_row_in_review(client, db, setup, sent):
    s = setup
    r = _create(client, s, [
        _task(s["project"].id, s["normal"]["id"]),
        _task(s["project"].id, s["rework"]["id"]),
    ])
    res = _submit(client, s, r["id"])
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "submitted"
    assert _row(body, s["normal"]["id"])["rework_approval_status"] is None
    assert _row(body, s["rework"]["id"])["rework_approval_status"] == "pending"
    assert len(_requests(db)) == 1


def test_split_day_records_the_half(client, db, setup, sent, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "REPORT_DAY_PARTS_ENABLED", True)
    s = setup
    body = {
        "report_date": TODAY,
        "report_mode": "split_day",
        "periods": [
            {"day_part": "first_half", "period_status": "work_at_office",
             "remarks": "morning", "tasks": [_task(s["project"].id, s["normal"]["id"])]},
            {"day_part": "second_half", "period_status": "work_at_office",
             "remarks": "afternoon rework", "tasks": [_task(s["project"].id, s["rework"]["id"], remark="")]},
        ],
    }
    res = client.post(WR, headers=s["header"], json=body)
    assert res.status_code == 201, res.text
    assert _submit(client, s, res.json()["id"]).status_code == 200
    [req] = _requests(db)
    assert req.day_part == "second_half"
    # Blank activity remark -> the half's own day remark.
    assert req.employee_remarks == "afternoon rework"
    assert "Day Part: Second Half" in sent[0]["text_body"]


# TEST 13: a repeated submit never duplicates the request or the email.
def test_repeated_submit_is_refused_without_duplicates(client, db, setup, sent):
    s = setup
    r = _create(client, s, [_task(s["project"].id, s["rework"]["id"])])
    assert _submit(client, s, r["id"]).status_code == 200
    again = _submit(client, s, r["id"])
    assert again.status_code in (409, 422)
    assert len(_requests(db)) == 1
    assert len(sent) == 1


# TEST 18: un-configuring the sub-activity leaves existing requests intact.
def test_removing_config_keeps_existing_request(client, db, setup, sent):
    s = setup
    r = _create(client, s, [_task(s["project"].id, s["rework"]["id"])])
    _submit(client, s, r["id"])
    client.put(
        f"{AM}/sub-activities/{s['rework']['id']}/approval",
        json={"requires_pm_approval": False},
        headers=s["pm"],
    )
    [req] = _requests(db)
    assert req.status == "pending"
    assert req.sub_activity_name == "Instrument Rework"
    got = client.get(f"{WR}/{r['id']}", headers=s["header"]).json()
    assert _row(got, s["rework"]["id"])["rework_approval_status"] == "pending"


def test_config_is_read_at_submit_not_at_draft(client, db, setup, sent):
    """A draft saved before the sub-activity was configured still needs
    approval when it is submitted after - future submissions follow the list."""
    s = setup
    plain = _sub(client, s["pm"], s["rework"]["parent_id"], "Cable Rework")
    r = _create(client, s, [_task(s["project"].id, plain["id"])])
    client.put(
        f"{AM}/sub-activities/{plain['id']}/approval",
        json={"requires_pm_approval": True},
        headers=s["pm"],
    )
    assert _submit(client, s, r["id"]).status_code == 200
    assert len(_requests(db)) == 1


def test_no_pm_email_without_work_email(client, db, setup, sent, make_user, make_employee, login):
    """No reachable work email -> the bell still lands, the submit still succeeds."""
    s = setup
    pm2 = make_user("pm2@x.com", role=UserRole.project_manager)
    make_employee(employee_code="PM2", user_id=pm2.id)  # no work_email
    s["emp"].reporting_pm_id = pm2.id
    db.add(s["emp"])
    db.commit()
    r = _create(client, s, [_task(s["project"].id, s["rework"]["id"])])
    assert _submit(client, s, r["id"]).status_code == 200
    assert sent == []
    assert len(_requests(db)) == 1
