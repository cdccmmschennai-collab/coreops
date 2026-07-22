"""Backend contract for the read-only Benchmark Guide.

The guide reuses the SAME authorized endpoint the Work Report activity selector
uses -- GET /activity-master/sub-activities?active_only=true -- with no new
route and no schema change. These tests pin the two things the guide relies on:

  1. Data source: the endpoint returns the FULL benchmark configuration the
     guide formats (type / value / period / unit / notes), straight from the
     Activity Master rows -- never a static constant.
  2. Authorization: the same restricted-activity filter the report dropdown uses
     runs in the backend, so an unauthorized restricted activity is never sent
     to the client (the guide never downloads-then-hides), an authorized one is,
     and inactive rows are excluded.
"""
import pytest

from app.modules.users.models import UserRole

AM = "/api/v1/activity-master"


# ── helpers ──────────────────────────────────────────────────────────────────

def _activity(client, h, name="ACT", **kw):
    res = client.post(f"{AM}/activities", json={"name": name, **kw}, headers=h)
    assert res.status_code == 201, res.text
    return res.json()


def _sub(client, h, activity_id, name="SUB", **kw):
    res = client.post(
        f"{AM}/activities/{activity_id}/sub-activities",
        json={"name": name, **kw},
        headers=h,
    )
    assert res.status_code == 201, res.text
    return res.json()


def _restrict(client, h, activity_id, employee_ids):
    return client.patch(
        f"{AM}/activities/{activity_id}/access-type",
        json={"access_type": "RESTRICTED", "employee_ids": [str(e) for e in employee_ids]},
        headers=h,
    )


def _guide(client, header):
    """The guide's data call: exactly what the frontend hook issues."""
    res = client.get(f"{AM}/sub-activities?active_only=true", headers=header)
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture()
def pm(client, auth_header):
    return auth_header(email="pm@x.com", role=UserRole.project_manager)


@pytest.fixture()
def make_worker(make_user, make_employee, login):
    def _make(email, code):
        u = make_user(email, role=UserRole.employee)
        e = make_employee(employee_code=code, user_id=u.id, first_name=code, last_name="W")
        return {"user": u, "emp": e, "header": login(email)}

    return _make


# ── data source: full benchmark configuration reaches the guide ───────────────

def test_guide_returns_full_benchmark_fields_from_the_db(client, pm, make_worker):
    a = _activity(client, pm, name="DOC IDB")
    _sub(
        client, pm, a["id"], name="MDR/VDR Consolidation",
        benchmark_type="NUMERIC_DAILY", benchmark_value=250,
        relevant_count_field="records", benchmark_period_days=1,
        benchmark_remarks="Coordinate with QC",
    )
    w = make_worker("emp@x.com", "E1")
    rows = _guide(client, w["header"])
    got = next(r for r in rows if r["name"] == "MDR/VDR Consolidation")

    # Every field the guide's formatter consumes is present and DB-sourced.
    assert got["activity_name"] == "DOC IDB"
    assert got["benchmark_type"] == "NUMERIC_DAILY"
    assert float(got["benchmark_value"]) == 250
    assert got["benchmark_period_days"] == 1
    assert got["relevant_count_field"] == "records"
    assert got["benchmark_remarks"] == "Coordinate with QC"
    assert got["is_active"] is True


def test_guide_reflects_a_benchmark_edit_without_code_change(client, pm, make_worker):
    a = _activity(client, pm, name="MTL")
    sub = _sub(
        client, pm, a["id"], name="O&M Manuals",
        benchmark_type="NUMERIC_DAILY", benchmark_value=500,
        relevant_count_field="pages", benchmark_period_days=1,
    )
    w = make_worker("emp@x.com", "E1")
    before = next(r for r in _guide(client, w["header"]) if r["id"] == sub["id"])
    assert float(before["benchmark_value"]) == 500

    # Edit the benchmark in Activity Master; the guide's next fetch shows it.
    upd = client.patch(
        f"{AM}/sub-activities/{sub['id']}", json={"benchmark_value": 750}, headers=pm
    )
    assert upd.status_code == 200, upd.text
    after = next(r for r in _guide(client, w["header"]) if r["id"] == sub["id"])
    assert float(after["benchmark_value"]) == 750


# ── authorization: filtering happens in the backend ───────────────────────────

def test_common_activity_appears_in_the_guide(client, pm, make_worker):
    a = _activity(client, pm, name="Open")
    sub = _sub(client, pm, a["id"])
    w = make_worker("emp@x.com", "E1")
    assert sub["id"] in {r["id"] for r in _guide(client, w["header"])}


def test_active_authorized_restricted_activity_appears(client, pm, make_worker):
    a = _activity(client, pm, name="Secret")
    sub = _sub(client, pm, a["id"])
    w = make_worker("emp@x.com", "E1")
    assert _restrict(client, pm, a["id"], [w["emp"].id]).status_code == 200
    assert sub["id"] in {r["id"] for r in _guide(client, w["header"])}


def test_unauthorized_restricted_activity_is_not_returned(client, pm, make_worker):
    a = _activity(client, pm, name="Secret")
    sub = _sub(client, pm, a["id"])
    w = make_worker("emp@x.com", "E1")
    _restrict(client, pm, a["id"], [w["emp"].id])
    other = make_worker("other@x.com", "E2")
    # The restricted sub-activity is filtered out server-side, not shipped+hidden.
    assert sub["id"] not in {r["id"] for r in _guide(client, other["header"])}


def test_inactive_activity_is_excluded(client, pm, make_worker):
    a = _activity(client, pm, name="Open")
    sub = _sub(client, pm, a["id"])
    w = make_worker("emp@x.com", "E1")
    client.delete(f"{AM}/activities/{a['id']}", headers=pm)  # soft-deactivate
    assert sub["id"] not in {r["id"] for r in _guide(client, w["header"])}
