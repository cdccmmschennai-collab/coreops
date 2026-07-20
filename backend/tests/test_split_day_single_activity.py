"""Split Day allows EXACTLY ONE activity per working half — enforced server-side.

The UI offers no way to add a second row, but the API is the authoritative
boundary: a hand-made, replayed or stale payload must be refused, never trimmed.
Extra rows are rejected rather than silently discarded, because dropping a row
the caller believed it saved loses real work.

Full-Day behaviour is unchanged and is pinned here too, so a regression in the
split rules can't quietly leak into the classic flow.
"""
import pytest

from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole

BASE = "/api/v1/work-reports"
TODAY = "2026-07-20"


@pytest.fixture()
def day_parts_on():
    from app.core.config import settings

    prev = settings.REPORT_DAY_PARTS_ENABLED
    settings.REPORT_DAY_PARTS_ENABLED = True
    try:
        yield
    finally:
        settings.REPORT_DAY_PARTS_ENABLED = prev


@pytest.fixture()
def setup_author(make_user, make_employee, make_project, make_project_member, login):
    def _make(*, email="emp@x.com", code="E-1", proj_code="P-1"):
        u = make_user(email, role=UserRole.employee)
        e = make_employee(employee_code=code, user_id=u.id)
        p = make_project(code=proj_code, status=ProjectStatus.active)
        make_project_member(project_id=p.id, employee_id=e.id)
        return {"user": u, "emp": e, "project": p, "header": login(email)}

    return _make


@pytest.fixture()
def pm_header(auth_header):
    return auth_header(email="pm@x.com", role=UserRole.project_manager)


def _task(project_id, sub_id=None, **counts):
    body = {"project_id": str(project_id), "description": "work"}
    if sub_id:
        body["sub_activity_id"] = sub_id
    body.update(counts)
    return body


def _split_payload(first, second, report_date=TODAY):
    return {
        "report_date": report_date,
        "report_mode": "split_day",
        "periods": [
            {"day_part": "first_half", **first},
            {"day_part": "second_half", **second},
        ],
    }


def _working(project_id, n=1):
    return {
        "period_status": "work_at_office",
        "location": "chennai",
        "tasks": [_task(project_id) for _ in range(n)],
    }


# ── create: the one-per-half cap ───────────────────────────────────────────


@pytest.mark.parametrize("part", ["first_half", "second_half"])
def test_create_rejects_two_tasks_in_a_half(client, setup_author, day_parts_on, part):
    a = setup_author()
    pid = a["project"].id
    halves = {"first_half": _working(pid), "second_half": _working(pid)}
    halves[part] = _working(pid, n=2)
    res = client.post(
        BASE, headers=a["header"],
        json=_split_payload(halves["first_half"], halves["second_half"]),
    )
    assert res.status_code == 422, res.text
    msg = res.json()["error"]["message"]
    assert "more than one activity" in msg
    assert ("First Half" if part == "first_half" else "Second Half") in msg


def test_create_rejects_three_tasks_in_a_half(client, setup_author, day_parts_on):
    a = setup_author()
    pid = a["project"].id
    res = client.post(
        BASE, headers=a["header"],
        json=_split_payload(_working(pid, n=3), _working(pid)),
    )
    assert res.status_code == 422, res.text


def test_valid_one_task_per_working_half_succeeds(client, setup_author, day_parts_on):
    a = setup_author()
    pid = a["project"].id
    res = client.post(
        BASE, headers=a["header"], json=_split_payload(_working(pid), _working(pid))
    )
    assert res.status_code == 201, res.text
    parts = {p["day_part"]: p for p in res.json()["periods"]}
    assert len(parts["first_half"]["tasks"]) == 1
    assert len(parts["second_half"]["tasks"]) == 1


def test_one_working_half_one_leave_half_succeeds(client, setup_author, day_parts_on):
    a = setup_author()
    res = client.post(BASE, headers=a["header"], json=_split_payload(
        _working(a["project"].id), {"period_status": "leave"},
    ))
    assert res.status_code == 201, res.text
    parts = {p["day_part"]: p for p in res.json()["periods"]}
    assert len(parts["first_half"]["tasks"]) == 1
    assert parts["second_half"]["tasks"] == []


# ── update: the same cap, same messages ────────────────────────────────────


def test_update_rejects_two_tasks_in_a_half(client, setup_author, day_parts_on):
    a = setup_author()
    pid = a["project"].id
    created = client.post(
        BASE, headers=a["header"], json=_split_payload(_working(pid), _working(pid))
    ).json()
    res = client.patch(f"{BASE}/{created['id']}", headers=a["header"], json={
        "report_mode": "split_day",
        "periods": [
            {"day_part": "first_half", **_working(pid, n=2)},
            {"day_part": "second_half", **_working(pid)},
        ],
    })
    assert res.status_code == 422, res.text

    # The stored report is untouched — a rejected update writes nothing.
    detail = client.get(f"{BASE}/{created['id']}", headers=a["header"]).json()
    parts = {p["day_part"]: p for p in detail["periods"]}
    assert len(parts["first_half"]["tasks"]) == 1
    assert len(parts["second_half"]["tasks"]) == 1


def test_update_rejects_task_on_nonworking_half(client, setup_author, day_parts_on):
    a = setup_author()
    pid = a["project"].id
    created = client.post(
        BASE, headers=a["header"], json=_split_payload(_working(pid), _working(pid))
    ).json()
    res = client.patch(f"{BASE}/{created['id']}", headers=a["header"], json={
        "report_mode": "split_day",
        "periods": [
            {"day_part": "first_half", **_working(pid)},
            {"day_part": "second_half", "period_status": "leave",
             "tasks": [_task(pid)]},
        ],
    })
    assert res.status_code == 422, res.text


# ── benchmark invariants are untouched by the cap ──────────────────────────


def test_split_fraction_stays_half_and_actuals_unscaled(
    client, db, setup_author, day_parts_on
):
    a = setup_author()
    pid = a["project"].id
    created = client.post(BASE, headers=a["header"], json=_split_payload(
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(pid, pages_count=40)]},
        {"period_status": "work_at_office", "location": "chennai",
         "tasks": [_task(pid, pages_count=60)]},
    )).json()
    fractions = sorted(str(p["work_fraction"])[:3] for p in created["periods"])
    assert fractions == ["0.5", "0.5"]
    # Actual counts are stored verbatim — a half period never halves them.
    assert sorted(t["pages_count"] for t in created["tasks"]) == [40, 60]


def test_nonworking_half_creates_no_period_task(client, setup_author, day_parts_on):
    a = setup_author()
    created = client.post(BASE, headers=a["header"], json=_split_payload(
        {"period_status": "week_off"}, _working(a["project"].id),
    )).json()
    parts = {p["day_part"]: p for p in created["periods"]}
    assert parts["first_half"]["tasks"] == []
    assert len(created["tasks"]) == 1


# ── Full Day is unaffected ─────────────────────────────────────────────────


def test_full_day_still_accepts_multiple_activities(client, setup_author):
    """The one-per-period cap is Split-Day only: Full Day keeps its existing
    multi-activity behaviour (Add Activity + the PM approval workflow)."""
    a = setup_author()
    pid = a["project"].id
    res = client.post(BASE, headers=a["header"], json={
        "report_date": TODAY,
        "day_status": "work_at_office",
        "location": "chennai",
        "tasks": [_task(pid), _task(pid), _task(pid)],
    })
    assert res.status_code == 201, res.text
    assert len(res.json()["tasks"]) == 3


def test_full_day_leave_still_drops_tasks_silently(client, setup_author):
    """Legacy Full-Day leniency is deliberately preserved — only Split Day
    rejects rows on a non-working period."""
    a = setup_author()
    res = client.post(BASE, headers=a["header"], json={
        "report_date": TODAY,
        "day_status": "leave",
        "tasks": [_task(a["project"].id)],
    })
    assert res.status_code == 201, res.text
    assert res.json()["tasks"] == []
