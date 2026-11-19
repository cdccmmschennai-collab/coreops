"""Rework Activity Approval - Phase 3: PM review (list / detail / approve / reject).

Covers spec tests 6, 7 (decision part), 9/10 (normal row untouched), 12, 14
(as decided: any PM may approve, never their own; employees never), 20, plus
filters, counts, pagination and the decision emails.
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
RA = "/api/v1/rework-approvals"
TODAY = date.today().isoformat()


def _sub(client, h, activity_id, name, approval=False):
    res = client.post(
        f"{AM}/activities/{activity_id}/sub-activities", json={"name": name}, headers=h
    )
    assert res.status_code == 201, res.text
    sub = res.json()
    if approval:
        client.put(
            f"{AM}/sub-activities/{sub['id']}/approval",
            json={"requires_pm_approval": True}, headers=h,
        )
    return sub


def _task(project_id, sub_id, remark="work"):
    return {"project_id": str(project_id), "description": remark, "sub_activity_id": str(sub_id)}


@pytest.fixture()
def sent(monkeypatch):
    out = []

    class _Result:
        queued, reason, task_id = True, None, "t"

    def fake_enqueue(**kw):
        out.append(kw)
        return _Result()

    monkeypatch.setattr(rework_email, "enqueue_email", fake_enqueue)
    return out


@pytest.fixture()
def s(client, make_user, make_employee, make_project, make_project_member, login, sent):
    pm_user = make_user("pm@x.com", role=UserRole.project_manager)
    make_employee(employee_code="PM1", first_name="Priya", last_name="PM",
                  user_id=pm_user.id, work_email="pm.work@x.com")
    pm2_user = make_user("pm2@x.com", role=UserRole.project_manager)
    make_employee(employee_code="PM2", first_name="Other", last_name="PM", user_id=pm2_user.id)
    emp_user = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="CDC031", first_name="ABIRAMI", last_name="S",
                        user_id=emp_user.id, reporting_pm_id=pm_user.id,
                        work_email="abirami.work@x.com")
    project = make_project(code="P1", name="Project A", status=ProjectStatus.active)
    make_project_member(project_id=project.id, employee_id=emp.id)
    pm = login("pm@x.com")
    act = client.post(f"{AM}/activities", json={"name": "INSTRUMENT ENGINEERING"}, headers=pm).json()
    return {
        "pm": pm, "pm2": login("pm2@x.com"), "emp": emp, "header": login("emp@x.com"),
        "project": project,
        "normal": _sub(client, pm, act["id"], "Instrument Design"),
        "rework": _sub(client, pm, act["id"], "Instrument Rework", approval=True),
        "sent": sent,
    }


def _submit_report(client, s, tasks, report_date=TODAY):
    body = {"report_date": report_date, "day_status": "work_at_office", "tasks": tasks}
    res = client.post(WR, headers=s["header"], json=body)
    assert res.status_code == 201, res.text
    rid = res.json()["id"]
    res = client.post(f"{WR}/{rid}/submit", headers=s["header"])
    assert res.status_code == 200, res.text
    return res.json()


def _only_request(client, s):
    page = client.get(RA, headers=s["pm"]).json()
    assert page["total"] == 1, page
    return page["items"][0]


def test_list_detail_and_remarks(client, s):
    _submit_report(client, s, [
        _task(s["project"].id, s["normal"]["id"]),
        _task(s["project"].id, s["rework"]["id"], remark="Loop drawing errors"),
    ])
    page = client.get(RA, headers=s["pm"]).json()
    assert page["counts"] == {"pending": 1, "approved": 0, "rejected": 0}
    item = page["items"][0]
    assert item["employee_code"] == "CDC031" and item["employee_name"] == "ABIRAMI S"
    assert item["activity_name"] == "INSTRUMENT ENGINEERING"
    assert item["sub_activity_name"] == "Instrument Rework"
    assert item["can_review"] is True

    detail = client.get(f"{RA}/{item['id']}", headers=s["pm"]).json()
    assert detail["employee_remarks"] == "Loop drawing errors"
    assert detail["report_status"] == "submitted"
    assert len(detail["history"]) == 1
    statuses = {a["sub_activity_name"]: a["rework_approval_status"] for a in detail["report_activities"]}
    assert statuses == {"Instrument Design": None, "Instrument Rework": "pending"}
    assert client.get(f"{RA}/pending-count", headers=s["pm"]).json() == {"count": 1}


# TEST 6 + approval email + normal row untouched.
def test_approve(client, db, s):
    report = _submit_report(client, s, [
        _task(s["project"].id, s["normal"]["id"]),
        _task(s["project"].id, s["rework"]["id"]),
    ])
    req = _only_request(client, s)
    s["sent"].clear()
    res = client.post(f"{RA}/{req['id']}/approve", json={}, headers=s["pm"])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "approved" and body["reviewer_name"] == "Priya PM"
    assert body["can_review"] is False

    got = client.get(f"{WR}/{report['id']}", headers=s["header"]).json()
    assert got["status"] == "submitted"
    rows = {t["sub_activity_name"]: t["rework_approval_status"] for t in got["tasks"]}
    assert rows == {"Instrument Design": None, "Instrument Rework": "approved"}

    [mail] = s["sent"]
    assert mail["to"] == "abirami.work@x.com"
    assert "Rework Approved" in mail["subject"]
    assert "Reviewed By: Priya PM" in mail["text_body"]
    assert client.get(f"{RA}/pending-count", headers=s["pm"]).json() == {"count": 0}


# TEST 7 / 9 / 10: reject marks only the rework row; normal row and report stay.
def test_reject_requires_remarks_and_keeps_normal_row(client, db, s):
    report = _submit_report(client, s, [
        _task(s["project"].id, s["normal"]["id"]),
        _task(s["project"].id, s["rework"]["id"]),
    ])
    req = _only_request(client, s)
    for bad in ({}, {"remarks": "   "}):
        res = client.post(f"{RA}/{req['id']}/reject", json=bad, headers=s["pm"])
        assert res.status_code == 422, res.text
    s["sent"].clear()
    res = client.post(
        f"{RA}/{req['id']}/reject", json={"remarks": "Not a rework - use design"}, headers=s["pm"]
    )
    assert res.status_code == 200, res.text
    assert res.json()["review_remarks"] == "Not a rework - use design"

    got = client.get(f"{WR}/{report['id']}", headers=s["header"]).json()
    assert got["status"] == "submitted"
    rows = {t["sub_activity_name"]: t["rework_approval_status"] for t in got["tasks"]}
    assert rows == {"Instrument Design": None, "Instrument Rework": "rejected"}

    [mail] = s["sent"]
    assert "Rework Rejected - Action Required" in mail["subject"]
    assert "Rejection Remarks: Not a rework - use design" in mail["text_body"]
    assert "resubmit" in mail["text_body"]
    bell = db.execute(
        select(Notification).where(Notification.type == "rework_approval_rejected")
    ).scalars().one()
    assert bell.target_url == f"/work-reports/{report['id']}"


# TEST 12 / 20: a decided request is never re-decided or overwritten.
def test_second_decision_is_refused(client, db, s):
    _submit_report(client, s, [_task(s["project"].id, s["rework"]["id"])])
    req = _only_request(client, s)
    assert client.post(f"{RA}/{req['id']}/approve", json={}, headers=s["pm"]).status_code == 200
    again = client.post(f"{RA}/{req['id']}/reject", json={"remarks": "late"}, headers=s["pm2"])
    assert again.status_code == 422
    db.expire_all()
    stored = db.get(ReworkApprovalRequest, req["id"])
    assert stored.status == "approved" and stored.review_remarks is None


# TEST 14 (as decided): employees can't decide or list; any other PM can decide.
def test_authorization(client, s):
    _submit_report(client, s, [_task(s["project"].id, s["rework"]["id"])])
    req = _only_request(client, s)
    assert client.get(RA, headers=s["header"]).status_code == 403
    assert client.post(f"{RA}/{req['id']}/approve", json={}, headers=s["header"]).status_code == 403
    # The owner may read their own request, read-only.
    own = client.get(f"{RA}/{req['id']}", headers=s["header"])
    assert own.status_code == 200 and own.json()["can_review"] is False
    # Any PM may decide (the existing PM-reviews-everything rule).
    assert client.post(f"{RA}/{req['id']}/approve", json={}, headers=s["pm2"]).status_code == 200


def test_unauthenticated_link_grants_nothing(client, s):
    _submit_report(client, s, [_task(s["project"].id, s["rework"]["id"])])
    req = _only_request(client, s)
    assert client.get(f"{RA}/{req['id']}").status_code == 401
    assert client.post(f"{RA}/{req['id']}/approve", json={}).status_code == 401


def test_pm_cannot_decide_own_request(client, db, s, make_project_member):
    """A PM who files their own report never approves their own rework."""
    pm_emp = db.execute(
        select(type(s["emp"])).where(type(s["emp"]).employee_code == "PM1")
    ).scalar_one()
    make_project_member(project_id=s["project"].id, employee_id=pm_emp.id)
    res = client.post(WR, headers=s["pm"], json={
        "report_date": TODAY, "day_status": "work_at_office",
        "tasks": [_task(s["project"].id, s["rework"]["id"])],
    })
    assert res.status_code == 201, res.text
    assert client.post(f"{WR}/{res.json()['id']}/submit", headers=s["pm"]).status_code == 200
    own = next(i for i in client.get(RA, headers=s["pm"]).json()["items"]
               if i["employee_code"] == "PM1")
    assert own["can_review"] is False
    assert client.post(f"{RA}/{own['id']}/approve", json={}, headers=s["pm"]).status_code == 403
    assert client.get(f"{RA}/pending-count", headers=s["pm"]).json() == {"count": 0}


def test_filters_counts_and_pagination(client, db, s):
    from datetime import timedelta

    for i in range(12):
        d = (date.today() - timedelta(days=i)).isoformat()
        _submit_report(client, s, [_task(s["project"].id, s["rework"]["id"])], report_date=d)
    first = client.get(RA, headers=s["pm"]).json()
    assert first["total"] == 12 and len(first["items"]) == 10
    second = client.get(f"{RA}?offset=10", headers=s["pm"]).json()
    assert len(second["items"]) == 2
    ids = {i["id"] for i in first["items"]} | {i["id"] for i in second["items"]}
    assert len(ids) == 12

    target = first["items"][0]
    client.post(f"{RA}/{target['id']}/approve", json={}, headers=s["pm"])
    page = client.get(f"{RA}?status=approved", headers=s["pm"]).json()
    assert page["total"] == 1
    assert page["counts"] == {"pending": 11, "approved": 1, "rejected": 0}

    by_date = client.get(f"{RA}?report_date={target['report_date']}", headers=s["pm"]).json()
    assert by_date["total"] == 1
    combo = client.get(
        f"{RA}?project_id={s['project'].id}&employee_id={s['emp'].id}"
        f"&sub_activity_id={s['rework']['id']}&status=pending",
        headers=s["pm"],
    ).json()
    assert combo["total"] == 11

    opts = client.get(f"{RA}/filter-options", headers=s["pm"]).json()
    assert [o["label"] for o in opts["employees"]] == ["CDC031 - ABIRAMI S"]
    assert [o["label"] for o in opts["activities"]] == ["INSTRUMENT ENGINEERING - Instrument Rework"]
    assert opts["projects"][0]["label"] == "P1 - Project A"
