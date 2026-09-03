"""Phase 4: `routed_to_name` - the "Routed to" line on the leave detail page.

The value is DERIVED, never stored. There is no migration behind this file: the
name comes from `recipients.resolve_in_app_recipient`, which reads the routed
project's CURRENT head and the requester's `reporting_pm_id`, both of which
already existed. Two properties matter and are asserted here:

  * it names THE PERSON WHO ACTUALLY GOT THE REQUEST - the same function the
    submission notification walks, so the page and the bell cannot disagree;
  * it is resolved FRESH, so a Head reassigned after the request was filed is
    honoured, exactly as approval authority is.

Once the request is SETTLED the answer stops being derived: "Routed to" is a
separate fact from "Approved by" and the card shows both, so it is read from the
submission notification actually delivered rather than re-resolved from the
project - a Head reassigned since must not rewrite who the request was sent to.

The decision actors (`manager_name`) are Phase 3's and are covered in
`test_leave_all_visibility.py`.
"""
import uuid
from datetime import date, timedelta

import pytest

from app.modules.employees.models import Employee
from app.modules.leave.models import LeaveStatus
from app.modules.notifications.models import Notification
from app.modules.users.models import UserRole

LIST = "/api/v1/leave-requests"


@pytest.fixture()
def cast(make_user, make_employee, make_project, login):
    """A requester with a reporting PM, plus a Head on a project they can be
    routed to.

    `reporting_pm_id` is a **users.id** - the fallback rung resolves it back to
    an employee row - so the PM's user is what gets passed here.
    """
    pm_user = make_user("pm@x.com", role=UserRole.project_manager)
    pm = make_employee(
        employee_code="PM1", first_name="Alex", last_name="Manager", user_id=pm_user.id
    )
    head_user = make_user("head@x.com", role=UserRole.employee)
    head = make_employee(
        employee_code="H1", first_name="NAINAR", last_name="B", user_id=head_user.id
    )
    emp_user = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(
        employee_code="E1",
        first_name="Santhosh",
        last_name="Kumar",
        user_id=emp_user.id,
        reporting_pm_id=pm_user.id,
    )
    project = make_project(code="P-1", head_employee_id=head.id)
    return {
        "pm": pm, "head": head, "employee": emp, "project": project,
        "pm_login": login("pm@x.com"),
        "emp_login": login("emp@x.com"),
        "head_login": login("head@x.com"),
    }


def _detail(client, headers, req_id) -> dict:
    res = client.get(f"{LIST}/{req_id}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _pending(make_leave_request, cast, **kw):
    return make_leave_request(
        employee_id=cast["employee"].id,
        start_date=date.today() + timedelta(days=7),
        end_date=date.today() + timedelta(days=7),
        **kw,
    )


# ---------- 1. pending names who is holding it ------------------------------

def test_a_routed_pending_request_names_the_project_head(
    client, cast, make_leave_request
):
    req = _pending(make_leave_request, cast, routed_project_id=cast["project"].id)
    assert _detail(client, cast["pm_login"], req.id)["routed_to_name"] == "NAINAR B"


def test_an_unrouted_pending_request_falls_back_to_the_reporting_pm(
    client, cast, make_leave_request
):
    """No routed project - the second rung of the existing chain, unchanged."""
    req = _pending(make_leave_request, cast)
    assert _detail(client, cast["pm_login"], req.id)["routed_to_name"] == "Alex Manager"


def test_the_head_is_resolved_fresh_not_frozen_at_submission(
    client, cast, make_leave_request, make_employee, make_user, db
):
    """A Head reassignment AFTER the request was filed is honoured.

    This is why the name is derived rather than stored: the request keeps its
    `routed_project_id`, and the person it reports is whoever heads that project
    now - which is also who may actually approve it.
    """
    req = _pending(make_leave_request, cast, routed_project_id=cast["project"].id)
    assert _detail(client, cast["pm_login"], req.id)["routed_to_name"] == "NAINAR B"

    new_head_user = make_user("head2@x.com", role=UserRole.employee)
    new_head = make_employee(
        employee_code="H2", first_name="GIRIDHARAN", last_name="SUBRAMANIAN",
        user_id=new_head_user.id,
    )
    cast["project"].head_employee_id = new_head.id
    db.commit()

    got = _detail(client, cast["pm_login"], req.id)["routed_to_name"]
    assert got == "GIRIDHARAN SUBRAMANIAN"


def test_a_head_with_no_login_falls_through_to_the_pm(
    client, cast, make_leave_request, make_employee
):
    """The in-app rule is "first candidate with a login" - the same test
    `_notify_routed_approver` applies, so the page names whoever's bell rang."""
    loginless_head = make_employee(employee_code="H3", first_name="No", last_name="Login")
    cast["project"].head_employee_id = loginless_head.id
    req = _pending(make_leave_request, cast, routed_project_id=cast["project"].id)
    assert _detail(client, cast["pm_login"], req.id)["routed_to_name"] == "Alex Manager"


def test_nobody_resolvable_is_a_null_not_an_error(
    client, make_user, make_employee, make_leave_request, login
):
    """An employee with no reporting PM and no routed project. The page simply
    omits the row."""
    u = make_user("lone@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="L1", user_id=u.id)
    make_user("pm2@x.com", role=UserRole.project_manager)
    req = make_leave_request(
        employee_id=emp.id,
        start_date=date.today() + timedelta(days=7),
        end_date=date.today() + timedelta(days=7),
    )
    body = _detail(client, login("pm2@x.com"), req.id)
    assert body["routed_to_name"] is None


# ---------- visibility: the requester sees it too ---------------------------

def test_the_employee_can_see_who_their_own_request_went_to(
    client, cast, make_leave_request
):
    """The point of the phase - informational, and NOT gated on review
    authority."""
    req = _pending(make_leave_request, cast, routed_project_id=cast["project"].id)
    body = _detail(client, cast["emp_login"], req.id)
    assert body["status"] == "pending"
    assert body["routed_to_name"] == "NAINAR B"


def test_a_head_reading_their_own_request_still_gets_no_review_authority(
    client, cast, make_leave_request, make_employee, make_user, db, login
):
    """Seeing an actor is not being allowed to act.

    The Head files their OWN leave on the project they head. They can read the
    routing line, and approving it is still refused by the unchanged
    `_assert_can_review`.
    """
    own = make_leave_request(
        employee_id=cast["head"].id,
        start_date=date.today() + timedelta(days=7),
        end_date=date.today() + timedelta(days=7),
        routed_project_id=cast["project"].id,
    )
    assert _detail(client, cast["head_login"], own.id)["status"] == "pending"

    res = client.post(f"{LIST}/{own.id}/approve", headers=cast["head_login"], json={})
    assert res.status_code == 403, res.text


# ---------- 2./3./4. a settled request keeps its routing --------------------

def _record_submission(db, req_id, user_id):
    """The submission notification exactly as `service._push` writes it.

    That row IS the record of who a request was routed to. The `make_*` fixtures
    insert rows straight into the table and so never send one; a request filed
    through `POST /leave-requests` always does.
    """
    db.add(
        Notification(
            user_id=user_id,
            type="leave_submitted",
            title="t",
            message="m",
            entity_type="leave_request",
            entity_id=req_id,
        )
    )
    db.commit()


def test_approving_keeps_routed_to_and_adds_the_decision_actor(
    client, cast, make_leave_request, db
):
    """ROUTED TO AND APPROVED BY ARE TWO DIFFERENT FACTS, and a decided request
    shows both. The Head received it; the PM approved it; neither name is allowed
    to stand in for the other."""
    req = _pending(make_leave_request, cast, routed_project_id=cast["project"].id)
    _record_submission(db, req.id, cast["head"].user_id)
    before = _detail(client, cast["pm_login"], req.id)
    assert (before["routed_to_name"], before["manager_name"]) == ("NAINAR B", None)

    res = client.post(f"{LIST}/{req.id}/approve", headers=cast["pm_login"], json={})
    assert res.status_code == 200, res.text

    after = _detail(client, cast["pm_login"], req.id)
    assert (after["routed_to_name"], after["manager_name"]) == ("NAINAR B", "Alex Manager")


def test_rejecting_does_the_same(client, cast, make_leave_request, db):
    req = _pending(make_leave_request, cast, routed_project_id=cast["project"].id)
    _record_submission(db, req.id, cast["head"].user_id)
    res = client.post(f"{LIST}/{req.id}/reject", headers=cast["pm_login"], json={})
    assert res.status_code == 200, res.text

    after = _detail(client, cast["pm_login"], req.id)
    assert after["routed_to_name"] == "NAINAR B"
    assert after["manager_name"] == "Alex Manager"


def test_a_settled_routing_is_history_not_a_fresh_lookup(
    client, cast, make_leave_request, make_employee, make_user, db
):
    """THE WHOLE REASON THE SETTLED ANSWER IS NOT DERIVED. Re-resolving the
    routed project after the fact would name whoever heads it TODAY; the request
    was sent to the Head who held the post then, and that must not change - which
    is the exact opposite of the pending rule asserted further up this file."""
    req = _pending(make_leave_request, cast, routed_project_id=cast["project"].id)
    _record_submission(db, req.id, cast["head"].user_id)
    res = client.post(f"{LIST}/{req.id}/approve", headers=cast["pm_login"], json={})
    assert res.status_code == 200, res.text

    new_head_user = make_user("head3@x.com", role=UserRole.employee)
    new_head = make_employee(
        employee_code="H3", first_name="GIRIDHARAN", last_name="SUBRAMANIAN",
        user_id=new_head_user.id,
    )
    cast["project"].head_employee_id = new_head.id
    db.commit()

    assert _detail(client, cast["pm_login"], req.id)["routed_to_name"] == "NAINAR B"


def test_a_settled_request_with_no_submission_on_record_says_nothing(
    client, cast, make_leave_request
):
    """No notification row - a request from before this was readable, or one whose
    recipient had no login. Null, never a guess from the current routing."""
    req = make_leave_request(
        employee_id=cast["employee"].id,
        start_date=date.today() + timedelta(days=7),
        end_date=date.today() + timedelta(days=7),
        status=LeaveStatus.approved,
        routed_project_id=cast["project"].id,
        manager_id=cast["pm"].id,
    )
    assert _detail(client, cast["pm_login"], req.id)["routed_to_name"] is None


@pytest.mark.parametrize(
    "status", [LeaveStatus.cancelled, LeaveStatus.cancellation_requested],
)
def test_the_cancellation_statuses_report_no_routing(
    client, cast, make_leave_request, db, status
):
    """Unchanged: those statuses show no actor row at all, so there is nothing to
    resolve and cancellation is out of scope here."""
    req = make_leave_request(
        employee_id=cast["employee"].id,
        start_date=date.today() + timedelta(days=7),
        end_date=date.today() + timedelta(days=7),
        status=status,
        routed_project_id=cast["project"].id,
        manager_id=cast["pm"].id,
    )
    _record_submission(db, req.id, cast["head"].user_id)
    assert _detail(client, cast["pm_login"], req.id)["routed_to_name"] is None


# ---------- the list is deliberately untouched ------------------------------

def test_the_all_leave_list_does_not_pay_for_routing(
    client, cast, make_leave_request
):
    """`routed_to_name` is a DETAIL-endpoint field. Resolving a Head and a PM per
    row would add two queries to every row of a 20-row page for a column the
    All-leave table does not have."""
    _pending(make_leave_request, cast, routed_project_id=cast["project"].id)
    res = client.get(LIST, headers=cast["pm_login"])
    assert res.status_code == 200, res.text
    assert [r["routed_to_name"] for r in res.json()["items"]] == [None]


# ---------- the notification and the page agree -----------------------------

def test_the_page_names_the_person_whose_bell_actually_rang(
    client, cast, make_leave_request, db
):
    """The property that makes this line trustworthy: the name the requester
    reads is the person the submission notification was actually delivered to.

    Filed through the real endpoint, so the notification is the real one. Both
    sides go through `recipients.resolve_in_app_recipient`, which is why they
    cannot drift - and this asserts it against the delivered row rather than
    against that function again.
    """
    res = client.post(
        LIST,
        headers=cast["emp_login"],
        json={
            "start_date": str(date.today() + timedelta(days=7)),
            "end_date": str(date.today() + timedelta(days=7)),
            "reason": "Family trip",
        },
    )
    assert res.status_code == 201, res.text
    req_id = res.json()["id"]

    displayed = _detail(client, cast["emp_login"], req_id)["routed_to_name"]
    notified = (
        db.query(Notification)
        .filter(
            Notification.entity_id == uuid.UUID(req_id),
            Notification.type == "leave_submitted",
        )
        .one()
    )
    recipient = db.query(Employee).filter(Employee.user_id == notified.user_id).one()
    assert displayed == recipient.full_name

    # And which rung that lands on here: no work report exists for this employee,
    # so `routing.resolve_routed_project` finds no project, the request is filed
    # with `routed_project_id` NULL, and the chain falls to the reporting PM.
    # Named explicitly so this test fails loudly if either side starts inventing
    # a routing the other does not share.
    assert displayed == "Alex Manager"
