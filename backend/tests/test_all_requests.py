"""Phase 4F - the unified All Requests history: `GET /api/v1/all-requests`.

The tab formerly called "All leave" now holds BOTH kinds. This file covers the
three things that could go wrong when two tables become one list:

  SCOPE      each kind keeps its OWN authorisation rule. A Project Head sees the
             requests routed to a project THEY head and no other Head's, and the
             union never widens what either module already allows.
  COMPLETENESS  leave rows are not displaced by permission rows or the reverse -
             one ORDER BY and one LIMIT over the union, so a page cannot silently
             drop a kind.
  FILTERS    the date window and the status filter mean the same thing they mean
             on each source list, on both kinds at once.

    docker exec wms-backend-1 pytest tests/test_all_requests.py
"""
from datetime import date

import pytest

from app.modules.leave.models import LeaveStatus
from app.modules.permissions.models import PermissionPeriod, PermissionStatus
from app.modules.users.models import UserRole

ALL = "/api/v1/all-requests"
LEAVE = "/api/v1/leave-requests"


def _d(iso: str) -> date:
    return date.fromisoformat(iso)


@pytest.fixture()
def team(make_user, make_employee, make_project, login):
    """A PM, two Heads with a project each, and one employee on each project.

    Two Heads is the whole point of the scope half: Head A must see A's rows and
    must NOT see B's, which is only observable when B's rows exist.
    """
    pm_u = make_user("pm@all.com", role=UserRole.project_manager)
    pm_e = make_employee(
        employee_code="PMA", first_name="Priya", last_name="Ramesh", user_id=pm_u.id
    )

    head_a_u = make_user("heada@all.com", role=UserRole.employee)
    head_a = make_employee(
        employee_code="HDA", first_name="Nainar", last_name="B", user_id=head_a_u.id
    )
    head_b_u = make_user("headb@all.com", role=UserRole.employee)
    head_b = make_employee(
        employee_code="HDB", first_name="Karthik", last_name="S", user_id=head_b_u.id
    )
    project_a = make_project(code="PA", head_employee_id=head_a.id)
    project_b = make_project(code="PB", head_employee_id=head_b.id)

    emp_a_u = make_user("empa@all.com", role=UserRole.employee)
    emp_a = make_employee(
        employee_code="EA", first_name="Santhosh", last_name="Kumar",
        user_id=emp_a_u.id, reporting_pm_id=pm_u.id,
    )
    emp_b_u = make_user("empb@all.com", role=UserRole.employee)
    emp_b = make_employee(
        employee_code="EB", first_name="Divya", last_name="R",
        user_id=emp_b_u.id, reporting_pm_id=pm_u.id,
    )

    return {
        "pm": login("pm@all.com"),
        "pm_employee": pm_e,
        "head_a": login("heada@all.com"),
        "head_a_employee": head_a,
        "head_b": login("headb@all.com"),
        "project_a": project_a,
        "project_b": project_b,
        "emp_a": emp_a,
        "emp_a_login": login("empa@all.com"),
        "emp_b": emp_b,
    }


def _rows(res) -> list[dict]:
    assert res.status_code == 200, res.text
    return res.json()["items"]


def _keys(res) -> set[tuple[str, str]]:
    """(kind, id) for every row - the identity that matters in a mixed list."""
    return {(r["kind"], r["id"]) for r in _rows(res)}


def _row(res, req_id: str) -> dict:
    return next(r for r in _rows(res) if r["id"] == req_id)


# ---------- 9. the list contains BOTH kinds ---------------------------------

def test_all_requests_contains_leave_and_permission_rows(
    client, team, make_leave_request, make_permission_request
):
    leave = make_leave_request(
        employee_id=team["emp_a"].id,
        start_date=_d("2027-03-02"), end_date=_d("2027-03-03"),
        routed_project_id=team["project_a"].id,
    )
    perm = make_permission_request(
        employee_id=team["emp_a"].id,
        permission_date=_d("2027-03-04"),
        period=PermissionPeriod.first_half_2h,
        routed_project_id=team["project_a"].id,
    )
    got = _keys(client.get(ALL, headers=team["pm"]))
    assert got == {("leave", str(leave.id)), ("permission", str(perm.id))}


def test_each_kind_carries_the_fields_its_own_column_needs(
    client, team, make_leave_request, make_permission_request
):
    """The Type cell is composed in the browser from the field each kind owns -
    a leave's Normal/Special classification, a permission's selected half - so
    no display string is invented server-side and neither module's existing
    label map is duplicated."""
    leave = make_leave_request(
        employee_id=team["emp_a"].id,
        start_date=_d("2027-03-02"), end_date=_d("2027-03-03"),
    )
    perm = make_permission_request(
        employee_id=team["emp_a"].id,
        permission_date=_d("2027-03-04"),
        period=PermissionPeriod.first_half_2h,
        duration_hours=2,
    )
    res = client.get(ALL, headers=team["pm"])

    lrow = _row(res, str(leave.id))
    assert lrow["classification"] in {"normal", "special"}
    assert lrow["from_date"] == "2027-03-02"
    assert lrow["to_date"] == "2027-03-03"
    assert lrow["period"] is None and lrow["duration_hours"] is None

    prow = _row(res, str(perm.id))
    assert prow["period"] == "first_half_2h"
    assert prow["duration_hours"] == 2
    # A permission is a single day, so both ends are that day - which is what
    # makes one date window serve both kinds.
    assert prow["from_date"] == prow["to_date"] == "2027-03-04"
    assert prow["classification"] is None


def test_a_permission_filed_before_the_period_column_still_renders(
    client, team, make_permission_request
):
    """A pre-Phase-4C row has no half on record; it must come back as a row with
    `period: null`, not vanish and not error."""
    perm = make_permission_request(
        employee_id=team["emp_a"].id,
        permission_date=_d("2027-03-04"),
        period=None,
        duration_hours=1,
    )
    row = _row(client.get(ALL, headers=team["pm"]), str(perm.id))
    assert row["period"] is None
    assert row["duration_hours"] == 1


# ---------- 5. the PM sees the permission history they are authorised for ----

def test_a_project_manager_sees_every_row_of_both_kinds(
    client, team, make_leave_request, make_permission_request
):
    """`_apply_scope` leaves a PM's query unfiltered in both modules, so the
    union does too - including rows routed to somebody else's project."""
    mine = make_permission_request(
        employee_id=team["emp_a"].id, permission_date=_d("2027-03-04"),
        period=PermissionPeriod.first_half_1h,
        routed_project_id=team["project_a"].id,
    )
    theirs = make_permission_request(
        employee_id=team["emp_b"].id, permission_date=_d("2027-03-05"),
        period=PermissionPeriod.first_half_1h,
        routed_project_id=team["project_b"].id,
    )
    unrouted = make_leave_request(
        employee_id=team["emp_b"].id,
        start_date=_d("2027-03-08"), end_date=_d("2027-03-08"),
    )
    got = _keys(client.get(ALL, headers=team["pm"]))
    assert got == {
        ("permission", str(mine.id)),
        ("permission", str(theirs.id)),
        ("leave", str(unrouted.id)),
    }


# ---------- 6/7. a Head sees THEIR routed project, and only theirs -----------

def test_a_head_sees_permission_history_routed_to_their_project(
    client, team, make_leave_request, make_permission_request
):
    perm = make_permission_request(
        employee_id=team["emp_a"].id, permission_date=_d("2027-03-04"),
        period=PermissionPeriod.first_half_1h,
        routed_project_id=team["project_a"].id,
        status=PermissionStatus.approved,
        manager_id=team["head_a_employee"].id,
    )
    leave = make_leave_request(
        employee_id=team["emp_a"].id,
        start_date=_d("2027-03-09"), end_date=_d("2027-03-10"),
        routed_project_id=team["project_a"].id,
    )
    got = _keys(client.get(ALL, headers=team["head_a"]))
    assert got == {("permission", str(perm.id)), ("leave", str(leave.id))}


def test_a_head_never_sees_another_heads_permission_history(
    client, team, make_leave_request, make_permission_request
):
    """The rule that must not be weakened to make the unified list work.

    Head A's project routes one permission and one leave; Head B's routes the
    other two. Head A gets exactly their own project's pair.
    """
    mine_p = make_permission_request(
        employee_id=team["emp_a"].id, permission_date=_d("2027-03-04"),
        period=PermissionPeriod.first_half_1h,
        routed_project_id=team["project_a"].id,
    )
    mine_l = make_leave_request(
        employee_id=team["emp_a"].id,
        start_date=_d("2027-03-11"), end_date=_d("2027-03-11"),
        routed_project_id=team["project_a"].id,
    )
    make_permission_request(
        employee_id=team["emp_b"].id, permission_date=_d("2027-03-05"),
        period=PermissionPeriod.first_half_1h,
        routed_project_id=team["project_b"].id,
    )
    make_leave_request(
        employee_id=team["emp_b"].id,
        start_date=_d("2027-03-12"), end_date=_d("2027-03-12"),
        routed_project_id=team["project_b"].id,
    )
    got = _keys(client.get(ALL, headers=team["head_a"]))
    assert got == {("permission", str(mine_p.id)), ("leave", str(mine_l.id))}


def test_an_unrouted_request_is_not_visible_to_any_head(
    client, team, make_permission_request
):
    """No `routed_project_id` means the PM fallback flow owns it. It must not
    leak into a Head's list, which is scoped on that column."""
    make_permission_request(
        employee_id=team["emp_b"].id, permission_date=_d("2027-03-05"),
        period=PermissionPeriod.first_half_1h, routed_project_id=None,
    )
    assert _keys(client.get(ALL, headers=team["head_a"])) == set()


def test_a_plain_employee_sees_only_their_own_of_both_kinds(
    client, team, make_leave_request, make_permission_request
):
    mine_p = make_permission_request(
        employee_id=team["emp_a"].id, permission_date=_d("2027-03-04"),
        period=PermissionPeriod.first_half_1h,
    )
    mine_l = make_leave_request(
        employee_id=team["emp_a"].id,
        start_date=_d("2027-03-13"), end_date=_d("2027-03-13"),
    )
    make_permission_request(
        employee_id=team["emp_b"].id, permission_date=_d("2027-03-05"),
        period=PermissionPeriod.first_half_1h,
    )
    make_leave_request(
        employee_id=team["emp_b"].id,
        start_date=_d("2027-03-14"), end_date=_d("2027-03-14"),
    )
    got = _keys(client.get(ALL, headers=team["emp_a_login"]))
    assert got == {("permission", str(mine_p.id)), ("leave", str(mine_l.id))}


def test_exclude_self_drops_the_readers_own_rows_of_both_kinds(
    client, team, make_leave_request, make_permission_request
):
    """A Project Head's reused panel passes this: nobody reviews their own, so
    their own rows must not sit in a list they are working through."""
    own = make_permission_request(
        employee_id=team["head_a_employee"].id, permission_date=_d("2027-03-06"),
        period=PermissionPeriod.first_half_1h,
        routed_project_id=team["project_a"].id,
    )
    other = make_leave_request(
        employee_id=team["emp_a"].id,
        start_date=_d("2027-03-15"), end_date=_d("2027-03-15"),
        routed_project_id=team["project_a"].id,
    )
    with_self = _keys(client.get(ALL, headers=team["head_a"]))
    assert ("permission", str(own.id)) in with_self

    without = _keys(
        client.get(ALL, headers=team["head_a"], params={"exclude_self": "true"})
    )
    assert without == {("leave", str(other.id))}


# ---------- 8. the existing Leave behaviour is intact ------------------------

def test_the_leave_list_endpoint_is_unchanged(
    client, team, make_leave_request, make_permission_request
):
    """Nothing was taken away from `/leave-requests` to build this: it still
    returns leave and ONLY leave, with the same shape it always had."""
    leave = make_leave_request(
        employee_id=team["emp_a"].id,
        start_date=_d("2027-03-02"), end_date=_d("2027-03-03"),
    )
    make_permission_request(
        employee_id=team["emp_a"].id, permission_date=_d("2027-03-04"),
        period=PermissionPeriod.first_half_1h,
    )
    body = client.get(LEAVE, headers=team["pm"]).json()
    assert [r["id"] for r in body["items"]] == [str(leave.id)]
    assert body["total"] == 1
    assert "classification" in body["items"][0]


def test_leave_rows_keep_their_employee_and_actor_names(
    client, team, make_leave_request
):
    leave = make_leave_request(
        employee_id=team["emp_a"].id,
        start_date=_d("2027-03-02"), end_date=_d("2027-03-03"),
        status=LeaveStatus.approved, manager_id=team["pm_employee"].id,
    )
    row = _row(client.get(ALL, headers=team["pm"]), str(leave.id))
    assert row["employee_name"] == "Santhosh Kumar"
    assert row["manager_name"] == "Priya Ramesh"


# ---------- the "By" column: the ACTUAL actor, on both kinds ----------------

def test_the_actor_on_a_permission_row_is_the_person_who_decided(
    client, team, make_permission_request
):
    """Decided through the real endpoint by the PM, on a request routed to Head
    A's project - so a value read from the routing would say "Nainar B"."""
    perm = make_permission_request(
        employee_id=team["emp_a"].id, permission_date=_d("2027-03-04"),
        period=PermissionPeriod.first_half_1h,
        routed_project_id=team["project_a"].id,
    )
    res = client.post(
        f"/api/v1/permission-requests/{perm.id}/approve", headers=team["pm"], json={}
    )
    assert res.status_code == 200, res.text

    row = _row(client.get(ALL, headers=team["pm"]), str(perm.id))
    assert row["manager_id"] == str(team["pm_employee"].id)
    assert row["manager_name"] == "Priya Ramesh"


def test_a_pending_permission_row_has_no_actor(client, team, make_permission_request):
    perm = make_permission_request(
        employee_id=team["emp_a"].id, permission_date=_d("2027-03-04"),
        period=PermissionPeriod.first_half_1h,
    )
    row = _row(client.get(ALL, headers=team["pm"]), str(perm.id))
    assert row["manager_id"] is None
    assert row["manager_name"] is None


# ---------- 10. the filters apply to both kinds -----------------------------

def test_the_status_filter_selects_both_kinds(
    client, team, make_leave_request, make_permission_request
):
    approved_l = make_leave_request(
        employee_id=team["emp_a"].id,
        start_date=_d("2027-03-02"), end_date=_d("2027-03-02"),
        status=LeaveStatus.approved, manager_id=team["pm_employee"].id,
    )
    approved_p = make_permission_request(
        employee_id=team["emp_a"].id, permission_date=_d("2027-03-04"),
        period=PermissionPeriod.first_half_1h,
        status=PermissionStatus.approved, manager_id=team["pm_employee"].id,
    )
    make_leave_request(
        employee_id=team["emp_a"].id,
        start_date=_d("2027-03-03"), end_date=_d("2027-03-03"),
        status=LeaveStatus.rejected, manager_id=team["pm_employee"].id,
    )
    make_permission_request(
        employee_id=team["emp_a"].id, permission_date=_d("2027-03-05"),
        period=PermissionPeriod.first_half_1h, status=PermissionStatus.rejected,
    )
    got = _keys(client.get(ALL, headers=team["pm"], params={"status": "approved"}))
    assert got == {("leave", str(approved_l.id)), ("permission", str(approved_p.id))}


def test_cancellation_requested_is_selectable_on_both_kinds(
    client, team, make_leave_request, make_permission_request
):
    """This is a history view, not a queue, so every status is reachable -
    including the one the Cancellation queue works from."""
    l = make_leave_request(
        employee_id=team["emp_a"].id,
        start_date=_d("2027-03-02"), end_date=_d("2027-03-02"),
        status=LeaveStatus.cancellation_requested,
    )
    p = make_permission_request(
        employee_id=team["emp_a"].id, permission_date=_d("2027-03-04"),
        period=PermissionPeriod.first_half_1h,
        status=PermissionStatus.cancellation_requested,
    )
    got = _keys(
        client.get(ALL, headers=team["pm"], params={"status": "cancellation_requested"})
    )
    assert got == {("leave", str(l.id)), ("permission", str(p.id))}


def test_the_date_window_reads_the_absence_not_the_filing_date(
    client, team, make_leave_request, make_permission_request
):
    """Both rows are created now, so `created_at` cannot separate them: only the
    absence's own dates can. Leave is judged by OVERLAP (a leave straddling an
    edge is in), a permission by its single day.
    """
    straddling = make_leave_request(   # 28 Feb - 2 Mar, overlaps the window
        employee_id=team["emp_a"].id,
        start_date=_d("2027-02-28"), end_date=_d("2027-03-02"),
    )
    inside = make_permission_request(
        employee_id=team["emp_a"].id, permission_date=_d("2027-03-03"),
        period=PermissionPeriod.first_half_1h,
    )
    make_leave_request(                # wholly after the window
        employee_id=team["emp_a"].id,
        start_date=_d("2027-04-01"), end_date=_d("2027-04-02"),
    )
    make_permission_request(           # wholly before it
        employee_id=team["emp_a"].id, permission_date=_d("2027-02-01"),
        period=PermissionPeriod.first_half_1h,
    )
    got = _keys(
        client.get(
            ALL, headers=team["pm"], params={"from": "2027-03-01", "to": "2027-03-05"}
        )
    )
    assert got == {("leave", str(straddling.id)), ("permission", str(inside.id))}


def test_both_window_bounds_are_inclusive_for_a_permission(
    client, team, make_permission_request
):
    first = make_permission_request(
        employee_id=team["emp_a"].id, permission_date=_d("2027-03-01"),
        period=PermissionPeriod.first_half_1h,
    )
    last = make_permission_request(
        employee_id=team["emp_a"].id, permission_date=_d("2027-03-05"),
        period=PermissionPeriod.first_half_1h,
    )
    got = _keys(
        client.get(
            ALL, headers=team["pm"], params={"from": "2027-03-01", "to": "2027-03-05"}
        )
    )
    assert got == {("permission", str(first.id)), ("permission", str(last.id))}


def test_the_window_and_the_status_filter_compose(
    client, team, make_leave_request, make_permission_request
):
    wanted = make_permission_request(
        employee_id=team["emp_a"].id, permission_date=_d("2027-03-03"),
        period=PermissionPeriod.first_half_1h,
        status=PermissionStatus.approved, manager_id=team["pm_employee"].id,
    )
    make_permission_request(  # right status, outside the window
        employee_id=team["emp_a"].id, permission_date=_d("2027-04-03"),
        period=PermissionPeriod.first_half_1h,
        status=PermissionStatus.approved, manager_id=team["pm_employee"].id,
    )
    make_leave_request(       # in the window, wrong status
        employee_id=team["emp_a"].id,
        start_date=_d("2027-03-02"), end_date=_d("2027-03-02"),
    )
    got = _keys(
        client.get(
            ALL,
            headers=team["pm"],
            params={"from": "2027-03-01", "to": "2027-03-05", "status": "approved"},
        )
    )
    assert got == {("permission", str(wanted.id))}


def test_an_unknown_status_is_ignored_rather_than_erroring(
    client, team, make_leave_request
):
    """A stale value left in a bookmarked URL must not 422 the page."""
    leave = make_leave_request(
        employee_id=team["emp_a"].id,
        start_date=_d("2027-03-02"), end_date=_d("2027-03-02"),
    )
    got = _keys(client.get(ALL, headers=team["pm"], params={"status": "nonsense"}))
    assert got == {("leave", str(leave.id))}


# ---------- paging over a mixed list ----------------------------------------

def test_paging_covers_every_row_of_both_kinds_exactly_once(
    client, team, make_leave_request, make_permission_request
):
    """The reason this is one endpoint rather than two merged in the browser.

    Six rows of alternating kinds, read three at a time: the two pages together
    must be all six, with nothing repeated and nothing dropped.
    """
    expected = set()
    for i in range(3):
        leave = make_leave_request(
            employee_id=team["emp_a"].id,
            start_date=_d(f"2027-03-0{i + 1}"), end_date=_d(f"2027-03-0{i + 1}"),
        )
        perm = make_permission_request(
            employee_id=team["emp_a"].id, permission_date=_d(f"2027-03-1{i}"),
            period=PermissionPeriod.first_half_1h,
        )
        expected |= {("leave", str(leave.id)), ("permission", str(perm.id))}

    first = client.get(ALL, headers=team["pm"], params={"limit": 3, "offset": 0})
    second = client.get(ALL, headers=team["pm"], params={"limit": 3, "offset": 3})
    assert first.json()["total"] == 6
    assert len(_rows(first)) == 3 and len(_rows(second)) == 3
    assert not (_keys(first) & _keys(second))
    assert _keys(first) | _keys(second) == expected


def test_the_total_counts_both_kinds(
    client, team, make_leave_request, make_permission_request
):
    make_leave_request(
        employee_id=team["emp_a"].id,
        start_date=_d("2027-03-02"), end_date=_d("2027-03-02"),
    )
    make_permission_request(
        employee_id=team["emp_a"].id, permission_date=_d("2027-03-04"),
        period=PermissionPeriod.first_half_1h,
    )
    body = client.get(ALL, headers=team["pm"], params={"limit": 1}).json()
    assert body["total"] == 2
    assert len(body["items"]) == 1


def test_the_order_is_newest_first_and_stable_across_pages(
    client, team, make_leave_request, make_permission_request
):
    """Deterministic order is what makes paging safe: `created_at DESC, id DESC`
    over the union, so two rows created in the same instant keep one order."""
    make_leave_request(
        employee_id=team["emp_a"].id,
        start_date=_d("2027-03-02"), end_date=_d("2027-03-02"),
    )
    make_permission_request(
        employee_id=team["emp_a"].id, permission_date=_d("2027-03-04"),
        period=PermissionPeriod.first_half_1h,
    )
    make_leave_request(
        employee_id=team["emp_a"].id,
        start_date=_d("2027-03-06"), end_date=_d("2027-03-06"),
    )
    whole = [(r["kind"], r["id"]) for r in _rows(client.get(ALL, headers=team["pm"]))]
    paged = []
    for offset in (0, 1, 2):
        paged += [
            (r["kind"], r["id"])
            for r in _rows(
                client.get(ALL, headers=team["pm"], params={"limit": 1, "offset": offset})
            )
        ]
    assert paged == whole
    created = [r["created_at"] for r in _rows(client.get(ALL, headers=team["pm"]))]
    assert created == sorted(created, reverse=True)


# ---------- the endpoint is read-only ---------------------------------------

def test_an_anonymous_caller_is_refused(client):
    assert client.get(ALL).status_code == 401
