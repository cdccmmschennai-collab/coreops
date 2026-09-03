"""Phase 4F - Permission Detail names the ACTUAL decision actor, not the routing.

The point of these tests is to pin down a claim rather than to add a feature:
`permission_requests.manager_id` is already stamped with the DECIDING employee by
`approve_permission_request` / `reject_permission_request`, so "Reviewed by" needs
no new column and no migration. They prove it by deciding through the real
endpoints and reading the actor back off the detail response - and, crucially, by
making the routed Head and the deciding PM DIFFERENT PEOPLE, so a value derived
from the current routing would be visibly wrong.

`routed_to_name` is the other half: who the request is waiting on right now. It
is derived per read from `routed_project_id`, pending only, exactly as
`LeaveRequestOut.routed_to_name` is.

    docker exec wms-backend-1 pytest tests/test_permission_reviewer.py
"""
from datetime import date

import pytest

from app.modules.permissions.models import PermissionPeriod, PermissionStatus
from app.modules.users.models import UserRole

API = "/api/v1/permission-requests"

# Far enough ahead that the month is never "closed" - the same constant
# `test_permissions_phase11.py` established for this reason.
PERM_DATE = date(2027, 3, 1)


@pytest.fixture()
def cast(make_user, make_employee, make_project, login):
    """A requester, the Head their request is ROUTED to, and a PM who decides.

    Three distinct people on purpose. The Head is the routed recipient and the PM
    is the actor, so any implementation that answered "Reviewed by" from the
    routing would name NAINAR and fail every assertion below.
    """
    pm_u = make_user("pm4f@x.com", role=UserRole.project_manager)
    pm_e = make_employee(
        employee_code="PM4F", first_name="Priya", last_name="Ramesh", user_id=pm_u.id
    )
    head_u = make_user("head4f@x.com", role=UserRole.employee)
    head_e = make_employee(
        employee_code="HD4F", first_name="Nainar", last_name="B", user_id=head_u.id
    )
    project = make_project(code="P4F", head_employee_id=head_e.id)

    emp_u = make_user("emp4f@x.com", role=UserRole.employee)
    emp_e = make_employee(
        employee_code="EM4F",
        first_name="Santhosh",
        last_name="Kumar",
        user_id=emp_u.id,
        reporting_pm_id=pm_u.id,
    )
    return {
        "pm": login("pm4f@x.com"),
        "pm_employee": pm_e,
        "head": login("head4f@x.com"),
        "head_employee": head_e,
        "employee": emp_e,
        "emp_login": login("emp4f@x.com"),
        "project": project,
    }


def _detail(client, headers, req_id):
    res = client.get(f"{API}/{req_id}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


# ---------- 1. approved: the actor, never the routed recipient ---------------

def test_approving_names_the_actual_approver_not_the_routed_head(
    client, cast, make_permission_request
):
    """The PM decides a request routed to a DIFFERENT person's project.

    `manager_id` therefore holds the PM, and `reviewer_name` renders the PM -
    while `routed_project_id` still points at the Head's project, unchanged. The
    two facts are separate and stay separate.
    """
    req = make_permission_request(
        employee_id=cast["employee"].id,
        permission_date=PERM_DATE,
        period=PermissionPeriod.first_half_1h,
        routed_project_id=cast["project"].id,
    )
    res = client.post(f"{API}/{req.id}/approve", headers=cast["pm"], json={})
    assert res.status_code == 200, res.text

    body = _detail(client, cast["pm"], req.id)
    assert body["status"] == "approved"
    assert body["manager_id"] == str(cast["pm_employee"].id)
    assert body["reviewer_name"] == "Priya Ramesh"
    # Routing is untouched by the decision, and is NOT what the reviewer field
    # was derived from.
    assert body["routed_project_id"] == str(cast["project"].id)
    assert body["reviewer_name"] != "Nainar B"


def test_a_head_approving_is_recorded_as_the_head(
    client, cast, make_permission_request
):
    """The mirror case: when the routed Head is the one who clicks, THEY are the
    recorded actor. The field follows the click, not the role."""
    req = make_permission_request(
        employee_id=cast["employee"].id,
        permission_date=PERM_DATE,
        period=PermissionPeriod.first_half_1h,
        routed_project_id=cast["project"].id,
    )
    res = client.post(f"{API}/{req.id}/approve", headers=cast["head"], json={})
    assert res.status_code == 200, res.text

    body = _detail(client, cast["head"], req.id)
    assert body["manager_id"] == str(cast["head_employee"].id)
    assert body["reviewer_name"] == "Nainar B"


# ---------- 2. rejected ------------------------------------------------------

def test_rejecting_names_the_actual_rejecter(client, cast, make_permission_request):
    req = make_permission_request(
        employee_id=cast["employee"].id,
        permission_date=PERM_DATE,
        period=PermissionPeriod.first_half_1h,
        routed_project_id=cast["project"].id,
    )
    res = client.post(
        f"{API}/{req.id}/reject", headers=cast["pm"], json={"comment": "no"}
    )
    assert res.status_code == 200, res.text

    body = _detail(client, cast["pm"], req.id)
    assert body["status"] == "rejected"
    assert body["reviewer_name"] == "Priya Ramesh"
    assert body["manager_comment"] == "no"


# ---------- 3. a cancellation decision ---------------------------------------

def test_a_cancellation_decision_keeps_the_approver_on_record(
    client, cast, make_permission_request
):
    """Deliberate, and the SAME rule leave follows.

    Approving a withdrawal does not overwrite `manager_id`: that column is the
    honest record of who GRANTED the permission, and losing it to record the
    cancellation would trade one true fact for another. No column currently
    stores a cancellation actor, so the frontend shows no actor against a
    cancelled row rather than naming the approver for an act they did not
    perform - see `leave/types.ts::leaveDecisionActor`, which the permission
    helper mirrors.
    """
    req = make_permission_request(
        employee_id=cast["employee"].id,
        permission_date=PERM_DATE,
        period=PermissionPeriod.first_half_1h,
        routed_project_id=cast["project"].id,
        status=PermissionStatus.approved,
        manager_id=cast["pm_employee"].id,
    )
    # The employee asks to withdraw it; the routed HEAD - a different person from
    # the approver - decides.
    res = client.post(
        f"{API}/{req.id}/request-cancellation", headers=cast["emp_login"], json={}
    )
    assert res.status_code == 200, res.text
    res = client.post(
        f"{API}/{req.id}/approve-cancellation", headers=cast["head"], json={}
    )
    assert res.status_code == 200, res.text

    body = _detail(client, cast["pm"], req.id)
    assert body["status"] == "cancelled"
    # Still the approver, not the Head who cancelled it - and not a guess.
    assert body["reviewer_name"] == "Priya Ramesh"


# ---------- 4. pending: no fabricated reviewer -------------------------------

def test_a_pending_request_has_no_reviewer_but_names_who_it_is_routed_to(
    client, cast, make_permission_request
):
    """Nobody has decided, so there is no actor to name - and the page must not
    borrow the routed recipient's name to fill the gap.

    What it DOES get is `routed_to_name`: the person actually holding the
    request, resolved fresh through the same chain the notification walks.
    """
    req = make_permission_request(
        employee_id=cast["employee"].id,
        permission_date=PERM_DATE,
        period=PermissionPeriod.first_half_1h,
        routed_project_id=cast["project"].id,
    )
    body = _detail(client, cast["pm"], req.id)
    assert body["status"] == "pending"
    assert body["manager_id"] is None
    assert body["reviewer_name"] is None
    assert body["routed_to_name"] == "Nainar B"


def test_routed_to_is_dropped_once_the_request_is_settled(
    client, cast, make_permission_request
):
    """Pending only. A decided request's routing is spent, and the question the
    page answers becomes "who decided this"."""
    req = make_permission_request(
        employee_id=cast["employee"].id,
        permission_date=PERM_DATE,
        period=PermissionPeriod.first_half_1h,
        routed_project_id=cast["project"].id,
    )
    assert client.post(f"{API}/{req.id}/approve", headers=cast["pm"], json={}).status_code == 200

    body = _detail(client, cast["pm"], req.id)
    assert body["routed_to_name"] is None
    assert body["reviewer_name"] == "Priya Ramesh"


def test_routed_to_falls_back_to_the_reporting_pm_when_there_is_no_head(
    client, cast, make_permission_request
):
    """An unrouted request is held by the requester's reporting PM - the same
    fallback rung `recipients.resolve_permission_recipients` delivers to, and
    never `Employee.manager_id`."""
    req = make_permission_request(
        employee_id=cast["employee"].id,
        permission_date=PERM_DATE,
        period=PermissionPeriod.first_half_1h,
        routed_project_id=None,
    )
    body = _detail(client, cast["pm"], req.id)
    assert body["routed_to_name"] == "Priya Ramesh"
