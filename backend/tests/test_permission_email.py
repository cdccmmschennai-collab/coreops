"""Tests for the permission submission email (Phase 4C).

Same two layers `test_leave_email.py` uses, and for the same reason:

  * Recipient and content behaviour are exercised directly against
    `permissions.email.send_submission_email`, with the `PermissionRequest` row
    built in place - independent of the working-day/routing matrix, which is
    `test_permission_routing.py`'s job.
  * The wiring - that submitting really does email exactly once, to the SAME
    person the in-app bell reaches - is exercised end to end through the API,
    because that is the property that would silently regress.

`enqueue_email` is replaced by a recorder in every test, so nothing reaches
Celery, Redis or SMTP.

    docker exec wms-backend-1 pytest tests/test_permission_email.py
"""
from datetime import date

import pytest

from app.modules.permissions import email as permission_email
from app.modules.permissions.models import (
    PermissionPeriod,
    PermissionRequest,
    PermissionStatus,
)
from app.modules.users.models import UserRole
from app.notifications.email_dispatch import EnqueueResult

API = "/api/v1/permission-requests"
PERMISSION_DATE = date(2027, 3, 1)


class _Recorder:
    """Stands in for `enqueue_email`, capturing what would have been queued."""

    def __init__(self, result=None):
        self.calls: list[dict] = []
        self._result = result or EnqueueResult(
            queued=True, task_id="task-1", recipients=()
        )

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self._result

    @property
    def recipients(self) -> list:
        return [c["to"] for c in self.calls]


@pytest.fixture()
def recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(permission_email, "enqueue_email", rec)
    return rec


class _StubSettings:
    EMAIL_ENABLED = True

    @property
    def is_configured(self):
        return True


def _permission(
    db, employee_id, *, routed_project_id=None,
    period: PermissionPeriod = PermissionPeriod.first_half_1h,
    reason="School run",
) -> PermissionRequest:
    from app.modules.permissions.models import PERIOD_HOURS

    req = PermissionRequest(
        employee_id=employee_id,
        permission_date=PERMISSION_DATE,
        duration_hours=PERIOD_HOURS[period],
        period=period,
        reason=reason,
        status=PermissionStatus.pending,
        routed_project_id=routed_project_id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def _pm(make_user, make_employee, tag: str, *, work_email: str | None):
    pm_user = make_user(f"perm-pm-{tag}@x.com", role=UserRole.project_manager)
    make_employee(employee_code=f"PPM{tag}", user_id=pm_user.id, work_email=work_email)
    return pm_user.id


# ---------- 1. Project Head routing -----------------------------------------

def test_a_routed_project_heads_work_email_is_the_recipient(
    db, make_user, make_employee, make_project, recorder,
):
    hu = make_user("perm-head-1@x.com")
    head = make_employee(
        employee_code="PHE1", first_name="Head", last_name="One",
        user_id=hu.id, work_email="phead.one@cdccmms.com",
    )
    project = make_project(code="PM-EM-1", head_employee_id=head.id)
    emp = make_employee(employee_code="PEE1", first_name="Karthikeyan", last_name="K")
    req = _permission(db, emp.id, routed_project_id=project.id)

    permission_email.send_submission_email(db, emp, req)

    assert recorder.recipients == ["phead.one@cdccmms.com"]
    assert recorder.calls[0]["subject"] == (
        "Permission Request - Karthikeyan K - Action Required"
    )


# ---------- 2. PM fallback ---------------------------------------------------

def test_no_usable_routed_project_falls_back_to_the_reporting_pm(
    db, make_user, make_employee, recorder,
):
    emp = make_employee(
        employee_code="PEE2",
        reporting_pm_id=_pm(make_user, make_employee, "2", work_email="ppm.two@cdccmms.com"),
    )
    req = _permission(db, emp.id, routed_project_id=None)

    permission_email.send_submission_email(db, emp, req)

    assert recorder.recipients == ["ppm.two@cdccmms.com"]


# ---------- 4. manager_id is never used -------------------------------------

def test_the_line_manager_is_never_the_permission_email_recipient(
    db, make_user, make_employee, recorder,
):
    """`manager_id` is the line manager and is not an authorized reviewer -
    the recipient must be `reporting_pm_id` even when the two differ."""
    mgr = make_employee(employee_code="PMG4", work_email="pmgr.four@cdccmms.com")
    emp = make_employee(
        employee_code="PEE4",
        manager_id=mgr.id,
        reporting_pm_id=_pm(make_user, make_employee, "4", work_email="ppm.four@cdccmms.com"),
    )
    req = _permission(db, emp.id, routed_project_id=None)

    permission_email.send_submission_email(db, emp, req)

    assert recorder.recipients == ["ppm.four@cdccmms.com"]
    assert "pmgr.four@cdccmms.com" not in recorder.recipients


# ---------- 5. delivery failure never blocks creation ------------------------

def test_a_dead_broker_does_not_raise(db, make_user, make_employee, monkeypatch):
    import app.notifications.email_dispatch as dispatch
    import app.tasks.email_tasks as email_tasks

    class _DeadTask:
        def delay(self, payload):
            raise OSError("connection refused")

    monkeypatch.setattr(email_tasks, "send_email", _DeadTask())
    monkeypatch.setattr(dispatch, "get_email_settings", lambda: _StubSettings())

    emp = make_employee(
        employee_code="PEE5",
        reporting_pm_id=_pm(make_user, make_employee, "5", work_email="ppm.five@cdccmms.com"),
    )
    req = _permission(db, emp.id)

    permission_email.send_submission_email(db, emp, req)  # must not raise


def test_a_renderer_failure_does_not_escape(db, make_user, make_employee, monkeypatch):
    emp = make_employee(
        employee_code="PEE6",
        reporting_pm_id=_pm(make_user, make_employee, "6", work_email="ppm.six@cdccmms.com"),
    )
    req = _permission(db, emp.id)

    def _boom(**kwargs):
        raise RuntimeError("template exploded")

    monkeypatch.setattr(permission_email, "render_submission_email", _boom)

    permission_email.send_submission_email(db, emp, req)  # must not raise


def test_nobody_reachable_sends_nothing_and_does_not_raise(db, make_employee, recorder):
    emp = make_employee(employee_code="PEE7", manager_id=None, reporting_pm_id=None)
    req = _permission(db, emp.id, routed_project_id=None)

    permission_email.send_submission_email(db, emp, req)

    assert recorder.calls == []


# ---------- 6. email contents -------------------------------------------------

def test_the_email_carries_the_actual_selected_option_not_the_plain_hour_count(
    db, make_user, make_employee, make_project, monkeypatch, recorder,
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "APP_BASE_URL", "https://coreops.cdccmms.com")

    hu = make_user("perm-head-8@x.com")
    head = make_employee(employee_code="PHE8", user_id=hu.id, work_email="phead.eight@cdccmms.com")
    project = make_project(code="PM-EM-8", head_employee_id=head.id)
    emp = make_employee(employee_code="PEE8", first_name="Nainar", last_name="B")
    req = _permission(
        db, emp.id, routed_project_id=project.id,
        period=PermissionPeriod.second_half_2h, reason="Medical appointment",
    )

    permission_email.send_submission_email(db, emp, req)

    body = recorder.calls[0]["text_body"]
    assert "Nainar B" in body
    assert "01 Mar 2027" in body
    # The actual selected option, never collapsed to a plain "2 hours".
    assert "2nd Half - 2 Hours" in body
    assert "2 hours" not in body
    assert "Medical appointment" in body
    assert f"https://coreops.cdccmms.com/attendance/permission/{req.id}" in body
    assert str(req.id) in body


def test_a_missing_reason_omits_the_row(db, make_user, make_employee, recorder):
    emp = make_employee(
        employee_code="PEE9",
        reporting_pm_id=_pm(make_user, make_employee, "9", work_email="ppm.nine@cdccmms.com"),
    )
    req = _permission(db, emp.id, reason=None)

    permission_email.send_submission_email(db, emp, req)

    assert "Reason:" not in recorder.calls[0]["text_body"]


def test_a_pre_phase_4c_request_with_no_period_falls_back_to_the_plain_hour_count(
    db, make_user, make_employee, recorder,
):
    """A row written before Phase 4C has no `period`. The email must still
    render something truthful rather than crash or invent a half."""
    emp = make_employee(
        employee_code="PEE10",
        reporting_pm_id=_pm(make_user, make_employee, "10", work_email="ppm.ten@cdccmms.com"),
    )
    req = PermissionRequest(
        employee_id=emp.id, permission_date=PERMISSION_DATE, duration_hours=2,
        period=None, status=PermissionStatus.pending,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    permission_email.send_submission_email(db, emp, req)

    assert "2 hours" in recorder.calls[0]["text_body"]


# ---------- 3. same recipient + 7. no duplicate --------------------------------

def test_submission_emails_the_same_recipient_the_bell_reaches_and_only_once(
    client, db, make_user, make_employee, make_project, make_project_member,
    login, recorder,
):
    from app.modules.notifications.models import Notification

    hu = make_user("perm-e2e-head@x.com")
    head = make_employee(
        employee_code="PHE20", user_id=hu.id, work_email="phead.e2e@cdccmms.com"
    )
    project = make_project(code="PM-EM-20", head_employee_id=head.id)

    eu = make_user("perm-e2e-emp@x.com")
    emp = make_employee(
        employee_code="PEE20", first_name="Karthikeyan", last_name="K", user_id=eu.id
    )
    make_project_member(project_id=project.id, employee_id=emp.id)

    from app.modules.calendar.working_days import next_working_day, previous_working_day
    from app.modules.work_reports import service as wr_svc
    from app.modules.work_reports.schemas import WorkReportCreate, WorkReportTaskIn
    from datetime import timedelta

    prev_day = previous_working_day(db, date.today() + timedelta(days=1))
    perm_date = next_working_day(db, prev_day)
    wr_svc.create_work_report(
        db, eu, WorkReportCreate(
            report_date=prev_day,
            tasks=[WorkReportTaskIn(
                project_id=project.id, description="work", minutes_spent=120
            )],
        ),
    )

    res = client.post(API, headers=login("perm-e2e-emp@x.com"), json={
        "permission_date": perm_date.isoformat(),
        "period": "first_half_1h",
        "reason": "x",
    })
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["routed_project_id"] == str(project.id)

    # Exactly one email, to the same Head the bell reached.
    assert len(recorder.calls) == 1
    assert recorder.recipients == ["phead.e2e@cdccmms.com"]

    note = db.query(Notification).filter(Notification.user_id == hu.id).one()
    assert note.type == "permission_submitted"
    assert note.target_url == f"/attendance/permission/{body['id']}"


def test_a_broker_outage_does_not_fail_the_submission(
    client, make_user, make_employee, login, monkeypatch,
):
    import app.notifications.email_dispatch as dispatch
    import app.tasks.email_tasks as email_tasks

    class _DeadTask:
        def delay(self, payload):
            raise OSError("connection refused")

    monkeypatch.setattr(email_tasks, "send_email", _DeadTask())
    monkeypatch.setattr(dispatch, "get_email_settings", lambda: _StubSettings())

    eu = make_user("perm-broker@x.com")
    make_employee(
        employee_code="PEE22", user_id=eu.id,
        reporting_pm_id=_pm(make_user, make_employee, "22", work_email="ppm.22@cdccmms.com"),
    )

    res = client.post(API, headers=login("perm-broker@x.com"), json={
        "permission_date": PERMISSION_DATE.isoformat(),
        "period": "first_half_1h",
        "reason": "x",
    })

    assert res.status_code == 201, res.text
    assert res.json()["status"] == "pending"
