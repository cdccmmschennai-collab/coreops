"""Leave cancellation.

Two paths:
  pending  -> cancelled                     employee, no review
  approved -> cancellation_requested        employee, leave that hasn't ended
  cancellation_requested -> cancelled|approved   project manager decides

Since Phase 10, cancelling an APPROVED leave reverses what its approval did: the
leave days come off the calendar and the deducted balance goes back. The tests
here pin the limits of that reversal - a day a human has since ruled on is never
removed, and leave that was never approved through the API (so never deducted)
is never credited. The forward direction lives in `test_leave_phase10.py`.

    docker exec wms-backend-1 pytest tests/test_leave_cancellation.py
"""
import threading
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.leave.models import LeaveRequest, LeaveStatus
from app.modules.leave_balances import ledger
from app.modules.leave_balances.models import EmployeeLeaveAdjustment
from app.modules.notifications.models import Notification
from app.modules.users.models import UserRole

API = "/api/v1/leave-requests"
TODAY = date.today()
NEXT_WEEK = TODAY + timedelta(days=7)
LAST_WEEK = TODAY - timedelta(days=7)


@pytest.fixture()
def team(make_user, make_employee):
    """A project manager plus one employee reporting to them."""
    mu = make_user("mgr@x.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MGR", user_id=mu.id)
    eu = make_user("emp@x.com", role=UserRole.employee)
    # `reporting_pm_id` (a users.id), not `manager_id`: the leave recipient chain
    # falls back to the reporting PM, who can actually decide the request.
    emp = make_employee(employee_code="EMP069", user_id=eu.id, reporting_pm_id=mu.id,
                        first_name="Arun", last_name="Kumar")
    return {"manager_user": mu, "manager": mgr, "employee_user": eu, "employee": emp}


@pytest.fixture()
def pending(make_leave_request, team):
    return make_leave_request(
        employee_id=team["employee"].id, start_date=NEXT_WEEK, end_date=NEXT_WEEK
    )


@pytest.fixture()
def approved(make_leave_request, team):
    """Approved future leave belonging to the team's employee."""
    return make_leave_request(
        employee_id=team["employee"].id,
        start_date=NEXT_WEEK,
        end_date=NEXT_WEEK + timedelta(days=2),
        status=LeaveStatus.approved,
        manager_id=team["manager"].id,
    )


def _request_cancellation(client, login, req_id, email="emp@x.com"):
    return client.post(f"{API}/{req_id}/request-cancellation", headers=login(email))


def _notifications(db, user_id, type_):
    return [
        n for n in db.query(Notification).filter(Notification.user_id == user_id).all()
        if n.type == type_
    ]


# ---------- the happy path --------------------------------------------------

def test_employee_cancels_own_pending_request(client, login, pending):
    res = client.post(f"{API}/{pending.id}/cancel", headers=login("emp@x.com"))
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "cancelled"


def test_cancelled_row_is_retained_in_history(client, login, pending, db):
    h = login("emp@x.com")
    client.post(f"{API}/{pending.id}/cancel", headers=h)

    db.expire_all()
    row = db.get(LeaveRequest, pending.id)
    assert row is not None
    assert row.status == LeaveStatus.cancelled

    history = client.get(API, headers=h).json()
    assert [i["id"] for i in history["items"]] == [str(pending.id)]
    assert history["items"][0]["status"] == "cancelled"


def test_cancel_response_carries_no_cancellation_metadata(client, login, pending):
    """The simplified feature stores no actor/timestamp/reason for a
    cancellation — the status alone is the record."""
    body = client.post(f"{API}/{pending.id}/cancel", headers=login("emp@x.com")).json()
    assert not [k for k in body if k.startswith("cancel")]


# ---------- authorization and status guards ---------------------------------

def test_cannot_cancel_another_employees_request(client, login, make_user,
                                                 make_employee, make_leave_request, team):
    other_u = make_user("other@x.com", role=UserRole.employee)
    other = make_employee(employee_code="OTH", user_id=other_u.id)
    req = make_leave_request(employee_id=other.id, start_date=NEXT_WEEK, end_date=NEXT_WEEK)

    res = client.post(f"{API}/{req.id}/cancel", headers=login("emp@x.com"))
    assert res.status_code == 403


def test_cannot_cancel_missing_request(client, login, team):
    res = client.post(
        f"{API}/00000000-0000-0000-0000-000000000000/cancel", headers=login("emp@x.com")
    )
    assert res.status_code == 404


@pytest.mark.parametrize(
    "status", [LeaveStatus.approved, LeaveStatus.rejected, LeaveStatus.cancelled]
)
def test_only_pending_requests_can_be_cancelled(client, login, make_leave_request,
                                                team, db, status):
    req = make_leave_request(employee_id=team["employee"].id, start_date=NEXT_WEEK,
                             end_date=NEXT_WEEK, status=status)
    res = client.post(f"{API}/{req.id}/cancel", headers=login("emp@x.com"))

    assert res.status_code == 409
    assert res.json()["error"]["message"] == "Only pending requests can be cancelled."
    db.expire_all()
    assert db.get(LeaveRequest, req.id).status == status


# ---------- the manager's view ----------------------------------------------

def test_cancelled_request_drops_out_of_the_pending_queue_and_count(client, login,
                                                                    pending):
    mgr_h = login("mgr@x.com")
    before = client.get(f"{API}?status=pending", headers=mgr_h).json()
    assert before["total"] == 1

    client.post(f"{API}/{pending.id}/cancel", headers=login("emp@x.com"))

    after = client.get(f"{API}?status=pending", headers=mgr_h).json()
    # the same query the PM dashboard badge counts
    assert after["total"] == 0
    assert after["items"] == []


# ---------- concurrency -----------------------------------------------------

def test_concurrent_approve_and_cancel_produce_one_winner(client, login, pending, db):
    """Both callers race on the same row. The FOR UPDATE lock serialises them,
    so exactly one succeeds and the loser sees a clean domain error."""
    emp_h, mgr_h = login("emp@x.com"), login("mgr@x.com")
    results: dict[str, int] = {}
    barrier = threading.Barrier(2)

    def cancel():
        barrier.wait()
        results["cancel"] = client.post(
            f"{API}/{pending.id}/cancel", headers=emp_h
        ).status_code

    def approve():
        barrier.wait()
        results["approve"] = client.post(
            f"{API}/{pending.id}/approve", headers=mgr_h, json={}
        ).status_code

    threads = [threading.Thread(target=cancel), threading.Thread(target=approve)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    succeeded = [k for k, v in results.items() if v == 200]
    assert len(succeeded) == 1, results

    db.expire_all()
    expected = (
        LeaveStatus.cancelled if succeeded == ["cancel"] else LeaveStatus.approved
    )
    assert db.get(LeaveRequest, pending.id).status == expected


# ---------- the existing workflow still works -------------------------------

def test_manager_approval_and_rejection_still_work(client, login, make_leave_request,
                                                   team, db):
    # Phase 10: approval draws down the balance, so an unfunded employee would
    # fail this on the balance guard rather than on the workflow it is testing.
    # Phase 3: funded by an opening adjustment, since there is no stored balance.
    db.add(EmployeeLeaveAdjustment(
        employee_id=team["employee"].id,
        effective_month=ledger.month_start(date.today()),
        days=Decimal("30.00"),
        reason="Opening balance",
    ))
    db.commit()
    mgr_h = login("mgr@x.com")
    to_approve = make_leave_request(employee_id=team["employee"].id,
                                    start_date=NEXT_WEEK, end_date=NEXT_WEEK)
    to_reject = make_leave_request(employee_id=team["employee"].id,
                                   start_date=NEXT_WEEK + timedelta(days=5),
                                   end_date=NEXT_WEEK + timedelta(days=6))

    approved = client.post(f"{API}/{to_approve.id}/approve", headers=mgr_h,
                           json={"comment": "Enjoy"})
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["manager_comment"] == "Enjoy"

    rejected = client.post(f"{API}/{to_reject.id}/reject", headers=mgr_h,
                           json={"comment": "Sprint deadline"})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


def test_cancelled_leave_is_not_a_deliverable_conflict(client, login, pending,
                                                       make_project,
                                                       make_project_member, team, db):
    from app.modules.project_deliverables.models import (
        DeliverableStatus,
        ProjectDeliverable,
    )

    project = make_project(code="P1")
    make_project_member(project_id=project.id, employee_id=team["employee"].id)
    db.add(ProjectDeliverable(project_id=project.id, name="Final drawings",
                              status=DeliverableStatus.planned, target_date=NEXT_WEEK))
    db.commit()

    mgr_h = login("mgr@x.com")
    before = client.post(f"{API}/deliverable-impact", headers=mgr_h,
                         json={"leave_request_ids": [str(pending.id)]}).json()
    assert len(before["items"]) == 1

    client.post(f"{API}/{pending.id}/cancel", headers=login("emp@x.com"))

    after = client.post(f"{API}/deliverable-impact", headers=mgr_h,
                        json={"leave_request_ids": [str(pending.id)]}).json()
    assert after["items"] == []


# ======================================================================
# Approved leave -> cancellation requested
# ======================================================================

def test_employee_requests_cancellation_of_own_approved_leave(client, login, approved,
                                                              team):
    res = _request_cancellation(client, login, approved.id)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "cancellation_requested"
    # the original approval is untouched
    assert body["manager_id"] == str(team["manager"].id)


def test_leave_covering_today_can_still_be_cancelled(client, login, make_leave_request,
                                                     team):
    """An employee who came back to work partway through an approved absence
    must still be able to withdraw it."""
    req = make_leave_request(employee_id=team["employee"].id,
                             start_date=TODAY - timedelta(days=1),
                             end_date=TODAY + timedelta(days=1),
                             status=LeaveStatus.approved)
    res = _request_cancellation(client, login, req.id)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "cancellation_requested"


def test_leave_starting_today_can_be_cancelled(client, login, make_leave_request, team):
    req = make_leave_request(employee_id=team["employee"].id, start_date=TODAY,
                             end_date=TODAY, status=LeaveStatus.approved)
    assert _request_cancellation(client, login, req.id).status_code == 200


def test_completely_past_approved_leave_cannot_be_cancelled(client, login,
                                                            make_leave_request, team):
    req = make_leave_request(employee_id=team["employee"].id, start_date=LAST_WEEK,
                             end_date=LAST_WEEK + timedelta(days=1),
                             status=LeaveStatus.approved)
    res = _request_cancellation(client, login, req.id)
    assert res.status_code == 422
    assert res.json()["error"]["message"] == "Past leave requests cannot be cancelled."


def test_cannot_request_cancellation_of_another_employees_leave(client, login,
                                                                make_user,
                                                                make_employee, approved):
    ou = make_user("other@x.com", role=UserRole.employee)
    make_employee(employee_code="OTH", user_id=ou.id)
    res = _request_cancellation(client, login, approved.id, email="other@x.com")
    assert res.status_code == 403


def test_pending_leave_cannot_enter_cancellation_requested(client, login, pending):
    res = _request_cancellation(client, login, pending.id)
    assert res.status_code == 409
    assert res.json()["error"]["message"] == (
        "Only approved leave requests can have cancellation requested."
    )


def test_duplicate_cancellation_request_fails(client, login, approved, db):
    assert _request_cancellation(client, login, approved.id).status_code == 200
    second = _request_cancellation(client, login, approved.id)
    assert second.status_code == 409
    assert second.json()["error"]["message"] == (
        "This leave already has a cancellation request awaiting review."
    )
    db.expire_all()
    assert db.get(LeaveRequest, approved.id).status == LeaveStatus.cancellation_requested


def test_pm_is_notified_once_about_the_cancellation_request(client, login, approved,
                                                            team, db):
    _request_cancellation(client, login, approved.id)
    _request_cancellation(client, login, approved.id)  # rejected, no second notification

    notes = _notifications(db, team["manager_user"].id, "leave_cancellation_requested")
    assert len(notes) == 1
    assert "EMP069 - Arun Kumar" in notes[0].message
    assert "requested cancellation of approved leave" in notes[0].message


# ======================================================================
# Project-manager review
# ======================================================================

def test_pm_approves_cancellation_and_leave_becomes_cancelled(client, login, approved,
                                                              db):
    _request_cancellation(client, login, approved.id)
    res = client.post(f"{API}/{approved.id}/approve-cancellation",
                      headers=login("mgr@x.com"))

    assert res.status_code == 200, res.text
    assert res.json()["status"] == "cancelled"
    db.expire_all()
    # the row is kept, not deleted
    assert db.get(LeaveRequest, approved.id).status == LeaveStatus.cancelled


def test_pm_rejects_cancellation_and_leave_returns_to_approved(client, login, approved,
                                                               team, db):
    _request_cancellation(client, login, approved.id)
    res = client.post(f"{API}/{approved.id}/reject-cancellation",
                      headers=login("mgr@x.com"))

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "approved"
    assert body["manager_id"] == str(team["manager"].id)
    db.expire_all()
    assert db.get(LeaveRequest, approved.id).status == LeaveStatus.approved


def test_employee_cannot_approve_or_reject_cancellation(client, login, approved):
    _request_cancellation(client, login, approved.id)
    emp_h = login("emp@x.com")
    for path in ("approve-cancellation", "reject-cancellation"):
        assert client.post(f"{API}/{approved.id}/{path}", headers=emp_h).status_code == 403


@pytest.mark.parametrize("path", ["approve-cancellation", "reject-cancellation"])
def test_reviewing_a_request_twice_fails(client, login, approved, path):
    _request_cancellation(client, login, approved.id)
    mgr_h = login("mgr@x.com")
    assert client.post(f"{API}/{approved.id}/{path}", headers=mgr_h).status_code == 200

    second = client.post(f"{API}/{approved.id}/{path}", headers=mgr_h)
    assert second.status_code == 409
    assert second.json()["error"]["message"] == (
        "This cancellation request has already been processed."
    )


def test_reviewing_leave_with_no_cancellation_request_fails(client, login, approved):
    res = client.post(f"{API}/{approved.id}/approve-cancellation",
                      headers=login("mgr@x.com"))
    assert res.status_code == 409


def test_employee_is_notified_once_per_decision(client, login, approved, team, db):
    _request_cancellation(client, login, approved.id)
    mgr_h = login("mgr@x.com")
    client.post(f"{API}/{approved.id}/approve-cancellation", headers=mgr_h)
    client.post(f"{API}/{approved.id}/approve-cancellation", headers=mgr_h)

    notes = _notifications(db, team["employee_user"].id, "leave_cancellation_approved")
    assert len(notes) == 1
    assert "was approved" in notes[0].message


def test_rejection_notification_says_the_leave_remains_active(client, login, approved,
                                                              team, db):
    _request_cancellation(client, login, approved.id)
    client.post(f"{API}/{approved.id}/reject-cancellation", headers=login("mgr@x.com"))

    notes = _notifications(db, team["employee_user"].id, "leave_cancellation_rejected")
    assert len(notes) == 1
    assert "remains active" in notes[0].message


def test_concurrent_cancellation_decisions_produce_one_winner(client, login, approved,
                                                              db):
    _request_cancellation(client, login, approved.id)
    mgr_h = login("mgr@x.com")
    results: dict[str, int] = {}
    barrier = threading.Barrier(2)

    def approve():
        barrier.wait()
        results["approve"] = client.post(
            f"{API}/{approved.id}/approve-cancellation", headers=mgr_h
        ).status_code

    def reject():
        barrier.wait()
        results["reject"] = client.post(
            f"{API}/{approved.id}/reject-cancellation", headers=mgr_h
        ).status_code

    threads = [threading.Thread(target=approve), threading.Thread(target=reject)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(results.values()) == [200, 409], results
    db.expire_all()
    assert db.get(LeaveRequest, approved.id).status in (
        LeaveStatus.cancelled, LeaveStatus.approved
    )


# ======================================================================
# What cancellation must NOT touch
# ======================================================================

def test_cancellation_preserves_a_day_the_pm_decided(client, login, approved, team,
                                                     make_attendance, db):
    """PHASE 10 changed what cancellation does to attendance.

    It used to touch nothing at all, because attendance was maintained entirely
    by hand. Now that an APPROVAL marks the leave days, cancelling has to unmark
    them - but only the ones that still look exactly like an approval wrote them.
    A day a human has since ruled on is still never touched, which is what this
    test now pins. `test_leave_phase10.py` covers the removal side.
    """
    marked_present = make_attendance(employee_id=team["employee"].id,
                                     attendance_date=NEXT_WEEK + timedelta(days=1),
                                     status=AttendanceStatus.present)
    # A leave day carrying a time is a human's entry, not an approval's.
    edited_leave = make_attendance(
        employee_id=team["employee"].id,
        attendance_date=NEXT_WEEK,
        status=AttendanceStatus.leave,
        check_in_at=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
    )

    _request_cancellation(client, login, approved.id)
    client.post(f"{API}/{approved.id}/approve-cancellation", headers=login("mgr@x.com"))

    db.expire_all()
    assert db.get(AttendanceRecord, edited_leave.id).status == AttendanceStatus.leave
    assert db.get(AttendanceRecord, marked_present.id).status == AttendanceStatus.present
    assert db.query(AttendanceRecord).count() == 2


def test_cancellation_restores_nothing_for_leave_approved_before_phase_10(
    client, login, approved, team, db
):
    """The `approved` fixture writes its row straight to the database, so no
    approval ever ran and no balance was ever deducted - exactly the shape of
    leave approved before Phase 10 existed. Reversal is defined as "restore what
    was actually removed", so there is nothing to remove and nothing to credit.
    """
    from app.modules.leave_balances.models import EmployeeLeaveBalanceHistory

    db.add(EmployeeLeaveAdjustment(
        employee_id=team["employee"].id,
        effective_month=ledger.month_start(date.today()),
        days=Decimal("12.50"),
        reason="Opening balance",
    ))
    db.commit()
    month = ledger.month_start(approved.end_date)

    _request_cancellation(client, login, approved.id)
    client.post(f"{API}/{approved.id}/approve-cancellation", headers=login("mgr@x.com"))

    db.expire_all()
    assert ledger.closing_balance(db, team["employee"].id, month) == Decimal("12.50")
    assert db.query(EmployeeLeaveBalanceHistory).count() == 0


def test_cancellation_response_carries_no_cancellation_metadata(client, login, approved):
    _request_cancellation(client, login, approved.id)
    body = client.post(f"{API}/{approved.id}/approve-cancellation",
                       headers=login("mgr@x.com")).json()
    assert not [k for k in body if k.startswith("cancel")]


# ======================================================================
# Queue counts, conflicts and the attendance summary
# ======================================================================

def test_queue_counts_are_correct(client, login, pending, approved):
    _request_cancellation(client, login, approved.id)
    mgr_h = login("mgr@x.com")

    assert client.get(f"{API}?status=pending", headers=mgr_h).json()["total"] == 1
    cancellations = client.get(
        f"{API}?status=cancellation_requested", headers=mgr_h
    ).json()
    assert cancellations["total"] == 1
    assert cancellations["items"][0]["id"] == str(approved.id)


def test_cancellation_requested_leave_is_still_an_active_conflict(
    client, login, approved, make_project, make_project_member, team, db
):
    from app.modules.project_deliverables.models import (
        DeliverableStatus,
        ProjectDeliverable,
    )

    project = make_project(code="P1")
    make_project_member(project_id=project.id, employee_id=team["employee"].id)
    db.add(ProjectDeliverable(project_id=project.id, name="Final drawings",
                              status=DeliverableStatus.planned, target_date=NEXT_WEEK))
    db.commit()
    mgr_h = login("mgr@x.com")

    _request_cancellation(client, login, approved.id)
    during = client.post(f"{API}/deliverable-impact", headers=mgr_h,
                         json={"leave_request_ids": [str(approved.id)]}).json()
    assert len(during["items"]) == 1

    # ...and drops out once the cancellation is granted
    client.post(f"{API}/{approved.id}/approve-cancellation", headers=mgr_h)
    after = client.post(f"{API}/deliverable-impact", headers=mgr_h,
                        json={"leave_request_ids": [str(approved.id)]}).json()
    assert after["items"] == []


def test_attendance_summary_reports_one_word_per_request(client, login, approved, team,
                                                         make_attendance):
    make_attendance(employee_id=team["employee"].id, attendance_date=NEXT_WEEK,
                    status=AttendanceStatus.present)
    make_attendance(employee_id=team["employee"].id,
                    attendance_date=NEXT_WEEK + timedelta(days=1),
                    status=AttendanceStatus.present)
    # outside the leave window - must not be counted
    make_attendance(employee_id=team["employee"].id,
                    attendance_date=NEXT_WEEK + timedelta(days=20),
                    status=AttendanceStatus.leave)

    res = client.post(f"{API}/attendance-summary", headers=login("mgr@x.com"),
                      json={"leave_request_ids": [str(approved.id)]})
    assert res.status_code == 200, res.text
    item = res.json()["items"][0]
    assert item["summary"] == "present"
    assert item["days_recorded"] == 2


def test_attendance_summary_flags_a_mixed_range(client, login, approved, team,
                                                make_attendance):
    make_attendance(employee_id=team["employee"].id, attendance_date=NEXT_WEEK,
                    status=AttendanceStatus.present)
    make_attendance(employee_id=team["employee"].id,
                    attendance_date=NEXT_WEEK + timedelta(days=1),
                    status=AttendanceStatus.leave)

    res = client.post(f"{API}/attendance-summary", headers=login("mgr@x.com"),
                      json={"leave_request_ids": [str(approved.id)]})
    assert res.json()["items"][0]["summary"] == "mixed"


def test_attendance_summary_reports_none_when_nothing_recorded(client, login, approved):
    res = client.post(f"{API}/attendance-summary", headers=login("mgr@x.com"),
                      json={"leave_request_ids": [str(approved.id)]})
    item = res.json()["items"][0]
    assert item["summary"] == "none"
    assert item["days_recorded"] == 0


def test_attendance_summary_is_pm_only(client, login, approved):
    res = client.post(f"{API}/attendance-summary", headers=login("emp@x.com"),
                      json={"leave_request_ids": [str(approved.id)]})
    assert res.status_code == 403
