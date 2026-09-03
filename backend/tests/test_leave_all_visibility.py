"""Phase 3: the All-leave queue's date window and its decision actor.

Two things are under test, both on `GET /leave-requests`:

1. `from` / `to` select on the LEAVE PERIOD, as an OVERLAP. A request counts as
   falling in the window when any part of the absence does - not only when the
   whole of it is contained, which is what these parameters used to mean and
   which silently hid every leave straddling either edge. `created_at` is never
   consulted.

2. `manager_name` - the "By" column - is the reviewer already recorded in
   `manager_id` at decision time. No new column and no migration: these tests
   exist partly to pin that down, by approving through the real endpoint and
   reading the actor back out of the list.

The window tests all use the same September window and vary only the leave's own
dates, so each case is the diagram from the spec:

    window            |-----------------|
                    09-01             09-05
"""
from datetime import date

import pytest

from app.modules.leave.models import LeaveStatus
from app.modules.users.models import UserRole

LIST = "/api/v1/leave-requests"

# The window every overlap case below is judged against.
WIN_FROM = "2026-09-01"
WIN_TO = "2026-09-05"
WINDOW = {"from": WIN_FROM, "to": WIN_TO}


def _d(iso: str) -> date:
    return date.fromisoformat(iso)


@pytest.fixture()
def team(make_user, make_employee, login):
    """A PM who can see everything, one requester, and one reviewer.

    The PM is the reader: `_apply_scope` leaves a project manager's query
    unfiltered, so every request created here lands in their All-leave list and
    the tests are about the FILTER, never about scope.
    """
    pm_user = make_user("pm@x.com", role=UserRole.project_manager)
    pm_emp = make_employee(
        employee_code="PM1", first_name="Priya", last_name="Ramesh", user_id=pm_user.id
    )
    emp_user = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(
        employee_code="E1", first_name="Santhosh", last_name="Kumar", user_id=emp_user.id
    )
    return {
        "pm_employee": pm_emp,
        "employee": emp,
        "pm": login("pm@x.com"),
        "emp_login": login("emp@x.com"),
    }


def _ids(res) -> set[str]:
    assert res.status_code == 200, res.text
    return {row["id"] for row in res.json()["items"]}


def _row(res, req_id: str) -> dict:
    assert res.status_code == 200, res.text
    return next(row for row in res.json()["items"] if row["id"] == req_id)


# ---------- C. no date filter -----------------------------------------------

def test_no_date_filter_returns_everything(client, team, make_leave_request):
    """The existing All-leave result is unchanged when no window is given."""
    inside = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-09-03"), end_date=_d("2026-09-04"),
    )
    far_away = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-11-20"), end_date=_d("2026-11-21"),
    )
    got = _ids(client.get(LIST, headers=team["pm"]))
    assert got == {str(inside.id), str(far_away.id)}


# ---------- D/E/F/G. the window is an overlap -------------------------------

def test_leave_wholly_inside_the_window_is_included(client, team, make_leave_request):
    #   leave                 |---|
    req = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-09-02"), end_date=_d("2026-09-03"),
    )
    assert _ids(client.get(LIST, headers=team["pm"], params=WINDOW)) == {str(req.id)}


def test_leave_completely_outside_the_window_is_excluded(client, team, make_leave_request):
    #   leave                                 |---|      (starts after 09-05)
    make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-09-06"), end_date=_d("2026-09-07"),
    )
    #   leave     |---|                                  (ends before 09-01)
    make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-08-24"), end_date=_d("2026-08-25"),
    )
    assert _ids(client.get(LIST, headers=team["pm"], params=WINDOW)) == set()


def test_leave_starting_before_the_window_and_ending_inside_is_included(
    client, team, make_leave_request
):
    #   leave        |------|                            (30 Aug - 2 Sep)
    req = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-08-30"), end_date=_d("2026-09-02"),
    )
    assert _ids(client.get(LIST, headers=team["pm"], params=WINDOW)) == {str(req.id)}


def test_leave_starting_inside_the_window_and_ending_after_is_included(
    client, team, make_leave_request
):
    #   leave                    |--------|              (3 Sep - 7 Sep)
    req = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-09-03"), end_date=_d("2026-09-07"),
    )
    assert _ids(client.get(LIST, headers=team["pm"], params=WINDOW)) == {str(req.id)}


def test_leave_spanning_the_whole_window_is_included(client, team, make_leave_request):
    #   leave     |-----------------------|              (straddles both edges)
    req = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-08-28"), end_date=_d("2026-09-10"),
    )
    assert _ids(client.get(LIST, headers=team["pm"], params=WINDOW)) == {str(req.id)}


def test_a_leave_touching_only_an_edge_counts(client, team, make_leave_request):
    """Both bounds are INCLUSIVE - a single day on 09-05 is in a window ending
    09-05, and one on 09-01 is in a window starting 09-01."""
    last = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-09-05"), end_date=_d("2026-09-05"),
    )
    first = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-09-01"), end_date=_d("2026-09-01"),
    )
    assert _ids(client.get(LIST, headers=team["pm"], params=WINDOW)) == {
        str(last.id), str(first.id)
    }


def test_the_window_reads_the_leave_period_not_the_request_date(
    client, team, make_leave_request
):
    """The point of the whole filter: a request FILED in August for September
    dates belongs to September, and one filed today for November does not.

    Both rows below are created now, so `created_at` cannot separate them - only
    the leave period can.
    """
    september = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-09-02"), end_date=_d("2026-09-03"),
    )
    make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-11-02"), end_date=_d("2026-11-03"),
    )
    assert _ids(client.get(LIST, headers=team["pm"], params=WINDOW)) == {str(september.id)}


# ---------- H/I. one bound on its own ---------------------------------------

def test_from_only_keeps_leave_still_running_on_or_after_that_date(
    client, team, make_leave_request
):
    ongoing = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-08-28"), end_date=_d("2026-09-02"),  # ends inside
    )
    later = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-09-20"), end_date=_d("2026-09-21"),
    )
    make_leave_request(  # finished before the bound
        employee_id=team["employee"].id,
        start_date=_d("2026-08-10"), end_date=_d("2026-08-11"),
    )
    got = _ids(client.get(LIST, headers=team["pm"], params={"from": WIN_FROM}))
    assert got == {str(ongoing.id), str(later.id)}


def test_to_only_keeps_leave_that_had_started_by_that_date(
    client, team, make_leave_request
):
    early = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-08-10"), end_date=_d("2026-08-11"),
    )
    straddling = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-09-04"), end_date=_d("2026-09-30"),  # starts inside
    )
    make_leave_request(  # begins after the bound
        employee_id=team["employee"].id,
        start_date=_d("2026-09-06"), end_date=_d("2026-09-07"),
    )
    got = _ids(client.get(LIST, headers=team["pm"], params={"to": WIN_TO}))
    assert got == {str(early.id), str(straddling.id)}


# ---------- J. window AND status --------------------------------------------

def test_the_date_window_and_the_status_filter_compose(
    client, team, make_leave_request
):
    """Neither filter changes the other's meaning - the result is the
    intersection."""
    wanted = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-09-02"), end_date=_d("2026-09-03"),
        status=LeaveStatus.approved, manager_id=team["pm_employee"].id,
    )
    make_leave_request(  # in the window, wrong status
        employee_id=team["employee"].id,
        start_date=_d("2026-09-04"), end_date=_d("2026-09-04"),
        status=LeaveStatus.rejected, manager_id=team["pm_employee"].id,
    )
    make_leave_request(  # right status, outside the window
        employee_id=team["employee"].id,
        start_date=_d("2026-10-12"), end_date=_d("2026-10-13"),
        status=LeaveStatus.approved, manager_id=team["pm_employee"].id,
    )
    got = _ids(
        client.get(LIST, headers=team["pm"], params={**WINDOW, "status": "approved"})
    )
    assert got == {str(wanted.id)}


# ---------- K/L. the "By" value is the actor the system ALREADY records ------

def test_approving_through_the_endpoint_names_the_approver(
    client, team, make_leave_request
):
    """No new field: approving stamps `manager_id`, and the list resolves that
    same id to the name the "By" column shows."""
    req = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-09-03"), end_date=_d("2026-09-03"),
    )
    res = client.post(f"{LIST}/{req.id}/approve", headers=team["pm"], json={})
    assert res.status_code == 200, res.text

    row = _row(client.get(LIST, headers=team["pm"]), str(req.id))
    assert row["status"] == "approved"
    assert row["manager_id"] == str(team["pm_employee"].id)
    assert row["manager_name"] == "Priya Ramesh"


def test_rejecting_through_the_endpoint_names_the_rejecter(
    client, team, make_leave_request
):
    req = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-09-03"), end_date=_d("2026-09-03"),
    )
    res = client.post(f"{LIST}/{req.id}/reject", headers=team["pm"], json={})
    assert res.status_code == 200, res.text

    row = _row(client.get(LIST, headers=team["pm"]), str(req.id))
    assert row["status"] == "rejected"
    assert row["manager_name"] == "Priya Ramesh"


def test_the_detail_endpoint_carries_the_same_actor(client, team, make_leave_request):
    req = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-09-03"), end_date=_d("2026-09-03"),
        status=LeaveStatus.approved, manager_id=team["pm_employee"].id,
    )
    res = client.get(f"{LIST}/{req.id}", headers=team["pm"])
    assert res.status_code == 200, res.text
    assert res.json()["manager_name"] == "Priya Ramesh"


# ---------- N. nobody has decided yet ---------------------------------------

def test_a_pending_request_has_no_actor(client, team, make_leave_request):
    req = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-09-03"), end_date=_d("2026-09-03"),
    )
    row = _row(client.get(LIST, headers=team["pm"]), str(req.id))
    assert row["manager_id"] is None
    assert row["manager_name"] is None


# ---------- M. cancelled: the ROW keeps the truth, the COLUMN stays blank ----

def test_a_cancelled_request_still_carries_the_approver_it_had(
    client, team, make_leave_request
):
    """Deliberate: a leave that was approved and then withdrawn keeps the
    approver in `manager_id`, because that is what happened.

    The "By" column shows an em dash for it all the same - the cancellation was a
    different act by a different person, and naming the approver against
    "Cancelled" would name the wrong one. That blanking is a display rule and is
    tested where it lives, in the frontend's `leaveDecisionActor`
    (`frontend/src/features/leave/types.actor.test.ts`); the API is not asked to
    forget the record.
    """
    req = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-09-03"), end_date=_d("2026-09-04"),
        status=LeaveStatus.cancelled, manager_id=team["pm_employee"].id,
    )
    row = _row(client.get(LIST, headers=team["pm"]), str(req.id))
    assert row["manager_name"] == "Priya Ramesh"


def test_the_requester_and_the_actor_are_named_the_same_way(
    client, team, make_leave_request
):
    """One id->name map serves both columns, so they cannot render differently."""
    req = make_leave_request(
        employee_id=team["employee"].id,
        start_date=_d("2026-09-03"), end_date=_d("2026-09-03"),
        status=LeaveStatus.approved, manager_id=team["pm_employee"].id,
    )
    row = _row(client.get(LIST, headers=team["pm"]), str(req.id))
    assert row["employee_name"] == "Santhosh Kumar"
    assert row["manager_name"] == "Priya Ramesh"
