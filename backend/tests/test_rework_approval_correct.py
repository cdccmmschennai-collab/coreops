"""Rework Activity Approval - Phase 4 (correct + resubmit) and Phase 5
(outstanding-report monitoring).

Covers spec tests 4, 7, 8, 9, 10, 11, 12, 15, 16, 17.
"""
from datetime import date

import pytest
from sqlalchemy import select

from app.modules.projects.models import ProjectStatus
from app.modules.rework_approvals import email as rework_email
from app.modules.rework_approvals.models import ReworkApprovalRequest
from app.modules.users.models import UserRole
from app.reminders.daily_report.service import DailyReportReminderService
from app.reminders.daily_report.template import render_daily_report_reminder

AM = "/api/v1/activity-master"
WR = "/api/v1/work-reports"
RA = "/api/v1/rework-approvals"


def _sub(client, h, activity_id, name, approval=False):
    sub = client.post(
        f"{AM}/activities/{activity_id}/sub-activities", json={"name": name}, headers=h
    ).json()
    if approval:
        client.put(
            f"{AM}/sub-activities/{sub['id']}/approval",
            json={"requires_pm_approval": True}, headers=h,
        )
    return sub


def _task(project_id, sub_id, remark="work"):
    return {"project_id": str(project_id), "description": remark, "sub_activity_id": str(sub_id)}


@pytest.fixture()
def s(client, db, make_user, make_employee, make_project, make_project_member, login, monkeypatch):
    sent = []

    class _Result:
        queued, reason, task_id = True, None, "t"

    monkeypatch.setattr(rework_email, "enqueue_email", lambda **kw: sent.append(kw) or _Result())

    pm_user = make_user("pm@x.com", role=UserRole.project_manager)
    make_employee(employee_code="PM1", first_name="Priya", last_name="PM",
                  user_id=pm_user.id, work_email="pm.work@x.com")
    emp_user = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="CDC031", first_name="ABIRAMI", last_name="S",
                        user_id=emp_user.id, reporting_pm_id=pm_user.id)
    project = make_project(code="P1", name="Project A", status=ProjectStatus.active)
    make_project_member(project_id=project.id, employee_id=emp.id)
    pm = login("pm@x.com")
    act = client.post(f"{AM}/activities", json={"name": "INSTRUMENT ENGINEERING"}, headers=pm).json()
    # The reminder only ever checks the previous working day, so file there.
    target = DailyReportReminderService().target_date(db, date.today())
    return {
        "pm": pm, "header": login("emp@x.com"), "emp": emp, "project": project,
        "normal": _sub(client, pm, act["id"], "Instrument Design"),
        "rework": _sub(client, pm, act["id"], "Instrument Rework", approval=True),
        "rework2": _sub(client, pm, act["id"], "Cable Rework", approval=True),
        "target": target, "sent": sent,
    }


def _submit(client, s, tasks):
    res = client.post(WR, headers=s["header"], json={
        "report_date": s["target"].isoformat(), "day_status": "work_at_office", "tasks": tasks,
    })
    assert res.status_code == 201, res.text
    res = client.post(f"{WR}/{res.json()['id']}/submit", headers=s["header"])
    assert res.status_code == 200, res.text
    return res.json()


def _rework_row(report, name="Instrument Rework"):
    return next(t for t in report["tasks"] if t["sub_activity_name"] == name)


def _reject(client, s, req_id, remarks="Not rework"):
    res = client.post(f"{RA}/{req_id}/reject", json={"remarks": remarks}, headers=s["pm"])
    assert res.status_code == 200, res.text


def _outstanding(db, s):
    reminders = DailyReportReminderService().collect(db, today=date.today())
    return [e for r in reminders for e in r.employees if e.employee_id == s["emp"].id]


# TEST 7 / 9 / 10 / 11 / 12: correcting a rejected row in a two-activity report.
def test_correct_rejected_row_keeps_normal_row_and_opens_new_cycle(client, db, s):
    report = _submit(client, s, [
        _task(s["project"].id, s["normal"]["id"], remark="design work"),
        _task(s["project"].id, s["rework"]["id"], remark="first try"),
    ])
    first_id = _rework_row(report)["rework_request_id"]
    _reject(client, s, first_id)
    normal_before = next(t for t in report["tasks"] if t["sub_activity_name"] == "Instrument Design")
    s["sent"].clear()

    res = client.post(
        f"{RA}/{first_id}/correct",
        json=_task(s["project"].id, s["rework"]["id"], remark="explained properly"),
        headers=s["header"],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "submitted"
    normal_after = next(t for t in body["tasks"] if t["sub_activity_name"] == "Instrument Design")
    assert normal_after["id"] == normal_before["id"]          # never rewritten
    assert normal_after["description"] == "design work"
    assert normal_after["rework_approval_status"] is None
    new_row = _rework_row(body)
    assert new_row["rework_approval_status"] == "pending"
    assert new_row["description"] == "explained properly"

    detail = client.get(f"{RA}/{new_row['rework_request_id']}", headers=s["pm"]).json()
    assert detail["cycle_no"] == 2
    assert [h["status"] for h in detail["history"]] == ["rejected", "pending"]
    assert detail["history"][0]["review_remarks"] == "Not rework"
    assert detail["history"][0]["employee_remarks"] == "first try"   # original kept
    assert len(s["sent"]) == 1                                         # PM told again
    assert "Resubmission: Attempt 2" in s["sent"][0]["text_body"]


# TEST 8: a one-activity rework report can be corrected (to a normal activity).
def test_correct_single_rework_report_to_normal_activity(client, db, s):
    report = _submit(client, s, [_task(s["project"].id, s["rework"]["id"])])
    req_id = _rework_row(report)["rework_request_id"]
    _reject(client, s, req_id)
    res = client.post(
        f"{RA}/{req_id}/correct",
        json=_task(s["project"].id, s["normal"]["id"], remark="actually design"),
        headers=s["header"],
    )
    assert res.status_code == 200, res.text
    [row] = res.json()["tasks"]
    assert row["sub_activity_name"] == "Instrument Design"
    assert row["rework_approval_status"] is None
    db.expire_all()
    statuses = [r.status for r in db.execute(select(ReworkApprovalRequest)).scalars()]
    assert statuses == ["rejected"]     # history kept, nothing new needed


def test_switch_to_other_rework_still_chains_history(client, db, s):
    report = _submit(client, s, [_task(s["project"].id, s["rework"]["id"])])
    req_id = _rework_row(report)["rework_request_id"]
    _reject(client, s, req_id)
    res = client.post(
        f"{RA}/{req_id}/correct",
        json=_task(s["project"].id, s["rework2"]["id"]),
        headers=s["header"],
    )
    assert res.status_code == 200, res.text
    new = _rework_row(res.json(), "Cable Rework")
    db.expire_all()
    stored = db.get(ReworkApprovalRequest, new["rework_request_id"])
    assert stored.cycle_no == 2 and str(stored.previous_request_id) == req_id


def test_correct_guards(client, db, s, make_user, make_employee, login):
    report = _submit(client, s, [_task(s["project"].id, s["rework"]["id"])])
    req_id = _rework_row(report)["rework_request_id"]
    body = _task(s["project"].id, s["rework"]["id"])
    # Pending (not rejected) -> refused.
    assert client.post(f"{RA}/{req_id}/correct", json=body, headers=s["header"]).status_code == 422
    _reject(client, s, req_id)
    # Someone else -> refused.
    other = make_user("other@x.com", role=UserRole.employee)
    make_employee(employee_code="EMP9", user_id=other.id)
    assert client.post(
        f"{RA}/{req_id}/correct", json=body, headers=login("other@x.com")
    ).status_code == 403
    # Correct once; the same rejected request can't be corrected twice.
    assert client.post(f"{RA}/{req_id}/correct", json=body, headers=s["header"]).status_code == 200
    assert client.post(f"{RA}/{req_id}/correct", json=body, headers=s["header"]).status_code == 422


# TEST 4 / 15 / 16 / 17 + resubmit: outstanding monitoring states.
def test_outstanding_monitoring_states(client, db, s):
    # No report -> listed normally.
    [e] = _outstanding(db, s)
    assert e.suffix == "" and e.display_name == "ABIRAMI S"

    # Only a rework activity, pending -> not missing, but IN REVIEW.
    report = _submit(client, s, [_task(s["project"].id, s["rework"]["id"])])
    [e] = _outstanding(db, s)
    assert e.display_name == "ABIRAMI S (IN REVIEW)"

    # Rejected -> REJECTED - ACTION REQUIRED.
    req_id = _rework_row(report)["rework_request_id"]
    _reject(client, s, req_id)
    [e] = _outstanding(db, s)
    assert e.display_name == "ABIRAMI S (REJECTED - ACTION REQUIRED)"

    # Corrected and resubmitted -> IN REVIEW again.
    res = client.post(
        f"{RA}/{req_id}/correct", json=_task(s["project"].id, s["rework"]["id"]),
        headers=s["header"],
    )
    new_id = _rework_row(res.json())["rework_request_id"]
    [e] = _outstanding(db, s)
    assert e.suffix == "IN REVIEW"

    # Approved -> removed from monitoring.
    client.post(f"{RA}/{new_id}/approve", json={}, headers=s["pm"])
    assert _outstanding(db, s) == []


def test_mixed_report_in_review_and_email_format(client, db, s):
    _submit(client, s, [
        _task(s["project"].id, s["normal"]["id"]),
        _task(s["project"].id, s["rework"]["id"]),
    ])
    reminders = DailyReportReminderService().collect(db, today=date.today())
    [reminder] = [r for r in reminders if any(e.employee_id == s["emp"].id for e in r.employees)]
    matching = [e for e in reminder.employees if e.employee_id == s["emp"].id]
    assert len(matching) == 1                     # never a duplicate row
    rendered = render_daily_report_reminder(reminder)
    assert "CDC031 - ABIRAMI S (IN REVIEW)" in rendered.text_body
    assert "CDC031 - ABIRAMI S (IN REVIEW)" in rendered.html_body
    assert "waiting for your approval" in rendered.text_body
    assert b"ABIRAMI S (IN REVIEW)" in rendered.csv_bytes


def test_export_rework_status_per_activity_row(client, db, s):
    """REWORK STATUS fills for the rework row only, and follows its lifecycle."""
    from io import BytesIO

    from openpyxl import load_workbook

    report = _submit(client, s, [
        _task(s["project"].id, s["normal"]["id"]),
        _task(s["project"].id, s["rework"]["id"]),
    ])
    day = s["target"].isoformat()

    def statuses():
        res = client.get(f"/api/v1/reports-export/activity-rows?from={day}&to={day}", headers=s["pm"])
        assert res.status_code == 200, res.text
        [row] = [r for r in res.json()["rows"] if r["employee_label"].startswith("CDC031")]
        return {a["sub_activity_type"]: a["rework_status"] for a in row["activities"]}

    assert statuses() == {"Instrument Design": None, "Instrument Rework": "IN REVIEW"}
    req_id = _rework_row(report)["rework_request_id"]
    _reject(client, s, req_id)
    assert statuses()["Instrument Rework"] == "REJECTED"

    res = client.post(
        f"{RA}/{req_id}/correct", json=_task(s["project"].id, s["rework"]["id"]),
        headers=s["header"],
    )
    client.post(f"{RA}/{_rework_row(res.json())['rework_request_id']}/approve", json={}, headers=s["pm"])
    assert statuses() == {"Instrument Design": None, "Instrument Rework": "APPROVED"}

    xlsx = client.get(f"/api/v1/reports-export/activity-rows.xlsx?from={day}&to={day}", headers=s["pm"])
    assert xlsx.status_code == 200
    ws = load_workbook(BytesIO(xlsx.content)).active
    headers = [c.value for c in ws[1]]
    sub_col = headers.index("SUB ACTIVITY TYPE")
    status_col = headers.index("REWORK STATUS")
    cells = {
        (row[sub_col].value or "").upper(): row[status_col].value
        for row in ws.iter_rows(min_row=2)
        if row[sub_col].value
    }
    assert cells["INSTRUMENT REWORK"] == "APPROVED"
    assert cells["INSTRUMENT DESIGN"] is None


def test_normal_report_is_not_outstanding(client, db, s):
    _submit(client, s, [_task(s["project"].id, s["normal"]["id"])])
    assert _outstanding(db, s) == []
