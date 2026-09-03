"""Phase 4E - cancellation of an APPROVED permission.

Three steps, the same shape leave has always had:

  approved               -> cancellation_requested        author asks
  cancellation_requested -> cancelled                     reviewer grants
  cancellation_requested -> approved                      reviewer refuses

What these pin, beyond the happy path:

  * the hours do NOT move when the withdrawal is merely requested - only a
    reviewer's decision moves them, in either direction;
  * the shared "Cancellation requests" queue is one list, `status=
    cancellation_requested`, carrying leave AND permission rows for the same
    reviewer;
  * authority is the EXISTING permission rule (`_assert_can_review`): the routed
    project's current Head, or a PM, and never yourself and never another Head.

    docker exec wms-backend-1 pytest tests/test_permission_cancellation.py
"""
from datetime import date, timedelta

import pytest

from app.modules.leave.models import LeaveStatus
from app.modules.permissions.models import PermissionPeriod, PermissionStatus
from app.modules.users.models import UserRole

API = "/api/v1/permission-requests"
LEAVE_API = "/api/v1/leave-requests"

# Far enough ahead that its month is never "closed" (see `_assert_month_open`),
# and never in the past for the "can't withdraw a finished absence" rule - the
# same constant `test_permission_routing.py` uses, for the same reason.
FUTURE = date(2027, 3, 1)
PAST = date.today() - timedelta(days=7)
NEXT_WEEK = date.today() + timedelta(days=7)


@pytest.fixture()
def cast(make_user, make_employee, make_project, make_project_member):
    """A Head with a project, an employee routed to it, a PM, and a second Head
    who heads a DIFFERENT project and must therefore be refused.

    `routed_project_id` is set directly on the request rather than grown from a
    work report: Phase 4B's resolver has its own exhaustive coverage in
    `test_leave_routing.py`/`test_permission_routing.py`, and what matters here
    is what the routed id then authorises.
    """
    head_u = make_user("chead@x.com")
    head = make_employee(employee_code="CH-1", user_id=head_u.id,
                         first_name="Priya", last_name="Raman")
    project = make_project(code="PC-1", head_employee_id=head.id)

    other_head_u = make_user("cohead@x.com")
    other_head = make_employee(employee_code="CH-2", user_id=other_head_u.id)
    make_project(code="PC-2", head_employee_id=other_head.id)

    pm_u = make_user("cpm@x.com", role=UserRole.project_manager)
    make_employee(employee_code="CPM-1", user_id=pm_u.id)

    eu = make_user("cemp@x.com")
    emp = make_employee(employee_code="CE-1", user_id=eu.id, reporting_pm_id=pm_u.id,
                        first_name="Santhosh", last_name="Kumar")
    make_project_member(project_id=project.id, employee_id=emp.id)

    return {
        "head_user": head_u, "head": head, "project": project,
        "other_head_user": other_head_u,
        "pm_user": pm_u,
        "employee_user": eu, "employee": emp,
    }


@pytest.fixture()
def approved(make_permission_request, cast):
    """An approved 1h permission routed to the cast's project."""
    return make_permission_request(
        employee_id=cast["employee"].id,
        permission_date=FUTURE,
        duration_hours=1,
        period=PermissionPeriod.first_half_1h,
        status=PermissionStatus.approved,
        manager_id=cast["head"].id,
        routed_project_id=cast["project"].id,
    )


def _request_cancellation(client, login, req_id, email="cemp@x.com"):
    return client.post(f"{API}/{req_id}/request-cancellation", headers=login(email))


def _balance(client, login, email="cemp@x.com", month=FUTURE):
    res = client.get(f"{API}/balance/me?month={month.isoformat()}", headers=login(email))
    assert res.status_code == 200, res.text
    return res.json()


# ---------- 1-3: requesting the withdrawal ---------------------------------

def test_approved_permission_can_request_cancellation(client, login, approved):
    res = _request_cancellation(client, login, approved.id)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "cancellation_requested"


@pytest.mark.parametrize(
    "status", [PermissionStatus.pending, PermissionStatus.rejected, PermissionStatus.cancelled]
)
def test_non_approved_permission_cannot_request_cancellation(
    client, login, make_permission_request, cast, status,
):
    req = make_permission_request(
        employee_id=cast["employee"].id, permission_date=FUTURE,
        period=PermissionPeriod.first_half_1h, status=status,
        routed_project_id=cast["project"].id,
    )
    res = _request_cancellation(client, login, req.id)
    assert res.status_code == 409, res.text


def test_a_finished_permission_cannot_be_withdrawn(
    client, login, make_permission_request, cast,
):
    """Nothing is left to withdraw once the day has gone - correcting the record
    afterwards is an attendance job, exactly as it is for leave."""
    req = make_permission_request(
        employee_id=cast["employee"].id, permission_date=PAST,
        period=PermissionPeriod.first_half_1h, status=PermissionStatus.approved,
        routed_project_id=cast["project"].id,
    )
    res = _request_cancellation(client, login, req.id)
    assert res.status_code == 422, res.text


def test_duplicate_cancellation_request_is_refused(client, login, approved):
    first = _request_cancellation(client, login, approved.id)
    assert first.status_code == 200, first.text

    second = _request_cancellation(client, login, approved.id)
    assert second.status_code == 409, second.text
    assert "awaiting review" in second.json()["error"]["message"]


def test_only_the_author_can_request_cancellation(client, login, approved):
    """Not even the reviewer files the employee's withdrawal for them."""
    res = _request_cancellation(client, login, approved.id, email="chead@x.com")
    assert res.status_code == 403, res.text


def test_the_author_cannot_one_step_cancel_an_approved_permission(
    client, login, approved,
):
    """The one-step `/cancel` survives for a PENDING request only. An approved
    permission is a granted absence and goes through the queue."""
    res = client.post(f"{API}/{approved.id}/cancel", headers=login("cemp@x.com"))
    assert res.status_code == 409, res.text

    res = client.get(f"{API}/{approved.id}", headers=login("cemp@x.com"))
    assert res.json()["status"] == "approved"


def test_the_author_can_still_one_step_cancel_a_pending_request(
    client, login, make_permission_request, cast,
):
    req = make_permission_request(
        employee_id=cast["employee"].id, permission_date=FUTURE,
        period=PermissionPeriod.first_half_1h, status=PermissionStatus.pending,
        routed_project_id=cast["project"].id,
    )
    res = client.post(f"{API}/{req.id}/cancel", headers=login("cemp@x.com"))
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "cancelled"


# ---------- the hours do not move until somebody rules ----------------------

def test_requesting_cancellation_does_not_give_the_hours_back(
    client, login, approved,
):
    before = _balance(client, login)
    assert before["approved_hours"] == 1
    assert before["remaining_hours"] == 3

    _request_cancellation(client, login, approved.id)

    after = _balance(client, login)
    assert after["approved_hours"] == 1, "an unreviewed ask must not free hours"
    assert after["remaining_hours"] == 3


def test_the_day_is_still_taken_while_the_withdrawal_is_under_review(
    client, login, approved,
):
    """One live permission per day - and one awaiting a withdrawal decision is
    still live, so a second request for the same day is refused."""
    _request_cancellation(client, login, approved.id)

    res = client.post(API, headers=login("cemp@x.com"), json={
        "permission_date": FUTURE.isoformat(), "period": "first_half_1h", "reason": "x",
    })
    assert res.status_code == 422, res.text


# ---------- 4-5: the SHARED cancellation queue ------------------------------

def test_permission_cancellation_appears_in_the_shared_queue(
    client, login, approved,
):
    _request_cancellation(client, login, approved.id)

    res = client.get(f"{API}?status=cancellation_requested", headers=login("chead@x.com"))
    assert res.status_code == 200, res.text
    ids = [r["id"] for r in res.json()["items"]]
    assert str(approved.id) in ids


def test_leave_cancellation_remains_visible_in_the_same_queue(
    client, login, cast, approved, make_leave_request,
):
    """The two halves of the queue are two calls with the same filter. Adding
    permission must not disturb the leave one - it is read here alongside a
    permission cancellation belonging to the same reviewer."""
    leave = make_leave_request(
        employee_id=cast["employee"].id,
        start_date=NEXT_WEEK, end_date=NEXT_WEEK,
        status=LeaveStatus.approved, manager_id=cast["head"].id,
        routed_project_id=cast["project"].id,
    )

    res = client.post(f"{LEAVE_API}/{leave.id}/request-cancellation",
                      headers=login("cemp@x.com"))
    assert res.status_code == 200, res.text
    _request_cancellation(client, login, approved.id)

    hdr = login("chead@x.com")
    leaves = client.get(f"{LEAVE_API}?status=cancellation_requested", headers=hdr)
    assert leaves.status_code == 200, leaves.text
    assert str(leave.id) in [r["id"] for r in leaves.json()["items"]]

    perms = client.get(f"{API}?status=cancellation_requested", headers=hdr)
    assert str(approved.id) in [r["id"] for r in perms.json()["items"]]


def test_the_queue_row_carries_the_employees_name(client, login, approved):
    """The reviewer's queue must render a human name, not eight characters of a
    UUID. `GET /employees` is scoped to their own row for a Head, so the name has
    to come off the request itself."""
    _request_cancellation(client, login, approved.id)

    res = client.get(f"{API}?status=cancellation_requested", headers=login("chead@x.com"))
    row = next(r for r in res.json()["items"] if r["id"] == str(approved.id))
    assert row["employee_name"] == "Santhosh Kumar"


def test_the_detail_page_carries_the_employees_name(client, login, approved):
    res = client.get(f"{API}/{approved.id}", headers=login("chead@x.com"))
    assert res.status_code == 200, res.text
    assert res.json()["employee_name"] == "Santhosh Kumar"
    assert res.json()["employee_code"] == "CE-1"


# ---------- 6-9: who may review it -----------------------------------------

def test_routed_project_head_can_review_the_cancellation(client, login, approved):
    _request_cancellation(client, login, approved.id)

    res = client.post(f"{API}/{approved.id}/approve-cancellation",
                      headers=login("chead@x.com"))
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "cancelled"


def test_pm_retains_review_access(client, login, approved):
    _request_cancellation(client, login, approved.id)

    res = client.post(f"{API}/{approved.id}/reject-cancellation",
                      headers=login("cpm@x.com"))
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"


def test_another_project_head_cannot_review_it(client, login, approved):
    _request_cancellation(client, login, approved.id)

    for endpoint in ("approve-cancellation", "reject-cancellation"):
        res = client.post(f"{API}/{approved.id}/{endpoint}",
                          headers=login("cohead@x.com"))
        assert res.status_code == 403, f"{endpoint}: {res.text}"


def test_self_review_remains_blocked(
    client, login, db, make_permission_request, cast,
):
    """A Head files their own permission and asks to withdraw it. They may not
    rule on it - somebody else has to."""
    own = make_permission_request(
        employee_id=cast["head"].id, permission_date=FUTURE,
        period=PermissionPeriod.first_half_1h, status=PermissionStatus.approved,
        routed_project_id=cast["project"].id,
    )
    res = _request_cancellation(client, login, own.id, email="chead@x.com")
    assert res.status_code == 200, res.text

    res = client.post(f"{API}/{own.id}/approve-cancellation", headers=login("chead@x.com"))
    assert res.status_code == 403, res.text


def test_exclude_self_drops_a_reviewers_own_cancellation_from_the_queue(
    client, login, make_permission_request, cast,
):
    own = make_permission_request(
        employee_id=cast["head"].id, permission_date=FUTURE,
        period=PermissionPeriod.first_half_1h, status=PermissionStatus.approved,
        routed_project_id=cast["project"].id,
    )
    _request_cancellation(client, login, own.id, email="chead@x.com")

    hdr = login("chead@x.com")
    plain = client.get(f"{API}?status=cancellation_requested", headers=hdr)
    assert str(own.id) in [r["id"] for r in plain.json()["items"]]

    filtered = client.get(
        f"{API}?status=cancellation_requested&exclude_self=true", headers=hdr
    )
    assert str(own.id) not in [r["id"] for r in filtered.json()["items"]]


# ---------- 10-12: the decision and what survives it ------------------------

def test_cancellation_approval_restores_the_hours(client, login, db, approved):
    _request_cancellation(client, login, approved.id)
    client.post(f"{API}/{approved.id}/approve-cancellation", headers=login("chead@x.com"))

    after = _balance(client, login)
    assert after["approved_hours"] == 0
    assert after["remaining_hours"] == 4

    db.expire_all()
    db.refresh(approved)
    assert approved.status == PermissionStatus.cancelled
    # The request itself is untouched apart from its status - the permission it
    # recorded is still readable in full.
    assert approved.permission_date == FUTURE
    assert approved.duration_hours == 1
    assert approved.period == PermissionPeriod.first_half_1h


def test_cancellation_rejection_leaves_the_permission_exactly_as_it_was(
    client, login, db, approved, cast,
):
    _request_cancellation(client, login, approved.id)
    client.post(f"{API}/{approved.id}/reject-cancellation", headers=login("chead@x.com"))

    after = _balance(client, login)
    assert after["approved_hours"] == 1, "a refused withdrawal must not move hours"
    assert after["remaining_hours"] == 3

    db.expire_all()
    db.refresh(approved)
    assert approved.status == PermissionStatus.approved
    # The ORIGINAL approver is still on the row - the cancellation decision does
    # not overwrite who granted the permission.
    assert approved.manager_id == cast["head"].id


def test_a_decided_cancellation_cannot_be_decided_twice(client, login, approved):
    _request_cancellation(client, login, approved.id)
    first = client.post(f"{API}/{approved.id}/approve-cancellation",
                        headers=login("chead@x.com"))
    assert first.status_code == 200, first.text

    second = client.post(f"{API}/{approved.id}/reject-cancellation",
                         headers=login("chead@x.com"))
    assert second.status_code == 409, second.text


def test_a_rejected_withdrawal_can_be_asked_for_again(client, login, approved):
    """Refusing the withdrawal returns the row to `approved`, which is a state a
    fresh request may be made from - it is not a one-shot."""
    _request_cancellation(client, login, approved.id)
    client.post(f"{API}/{approved.id}/reject-cancellation", headers=login("chead@x.com"))

    again = _request_cancellation(client, login, approved.id)
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "cancellation_requested"
