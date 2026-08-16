"""Phase 9A - GET /biometric/daily-review: employee search + pagination.

`counts` must always describe the whole day; `q` and pagination only ever
narrow/slice `items`. Mirrors the fixture style in
test_biometric_mapping_admin.py (client / pm / db / make_employee).
"""
from datetime import datetime, timezone

import pytest

from app.modules.biometric.models import BiometricEmployeeMapping, BiometricPunch
from app.modules.users.models import UserRole

REVIEW = "/api/v1/biometric/daily-review"
DAY = "2026-08-11"


@pytest.fixture()
def pm(auth_header):
    return auth_header("pm-review@x.com", role=UserRole.project_manager)


def _punch_present(db, employee, *, code: str):
    """One employee, two punches on DAY -> classification `present`."""
    db.add(
        BiometricEmployeeMapping(
            provider="easytime",
            external_employee_code=code,
            employee_id=employee.id,
            is_active=True,
        )
    )
    for hh in (9, 17):
        db.add(
            BiometricPunch(
                provider="easytime",
                external_transaction_id=f"txn-{code}-{hh}",
                external_employee_code=code,
                employee_id=None,
                punch_time=datetime(2026, 8, 11, hh - 5, 30, tzinfo=timezone.utc),
                received_at=datetime.now(timezone.utc),
                raw_punch_state="0",
            )
        )
    db.commit()


def test_pagination_slices_items_but_not_counts(client, pm, db, make_employee):
    for i in range(20):
        emp = make_employee(employee_code=f"E{i:03d}", first_name=f"Emp{i}", last_name="Test")
        _punch_present(db, emp, code=f"E{i:03d}")

    page1 = client.get(REVIEW, params={"date": DAY, "limit": 15, "offset": 0}, headers=pm)
    assert page1.status_code == 200, page1.text
    body1 = page1.json()
    assert len(body1["items"]) == 15
    assert body1["total"] >= 20
    assert body1["limit"] == 15
    assert body1["offset"] == 0
    assert body1["counts"]["present"] >= 20

    page2 = client.get(REVIEW, params={"date": DAY, "limit": 15, "offset": 15}, headers=pm)
    body2 = page2.json()
    assert body2["counts"] == body1["counts"]
    assert {r["employee_id"] for r in body2["items"]}.isdisjoint(
        {r["employee_id"] for r in body1["items"]}
    )


def test_default_limit_is_fifteen(client, pm, db, make_employee):
    for i in range(20):
        emp = make_employee(employee_code=f"F{i:03d}", first_name=f"F{i}", last_name="Test")
        _punch_present(db, emp, code=f"F{i:03d}")

    res = client.get(REVIEW, params={"date": DAY}, headers=pm)
    assert res.status_code == 200, res.text
    assert len(res.json()["items"]) == 15
    assert res.json()["limit"] == 15


def test_search_matches_name_or_code(client, pm, db, make_employee):
    alice = make_employee(employee_code="A100", first_name="Alice", last_name="Zephyr")
    bob = make_employee(employee_code="B200", first_name="Bob", last_name="Yankee")
    _punch_present(db, alice, code="A100")
    _punch_present(db, bob, code="B200")

    by_name = client.get(REVIEW, params={"date": DAY, "q": "alice"}, headers=pm).json()
    assert [r["employee_id"] for r in by_name["items"]] == [str(alice.id)]

    by_code = client.get(REVIEW, params={"date": DAY, "q": "b200"}, headers=pm).json()
    assert [r["employee_id"] for r in by_code["items"]] == [str(bob.id)]


def test_search_does_not_change_counts(client, pm, db, make_employee):
    alice = make_employee(employee_code="A101", first_name="Alice", last_name="Zephyr")
    bob = make_employee(employee_code="B201", first_name="Bob", last_name="Yankee")
    _punch_present(db, alice, code="A101")
    _punch_present(db, bob, code="B201")

    unfiltered = client.get(REVIEW, params={"date": DAY}, headers=pm).json()
    filtered = client.get(REVIEW, params={"date": DAY, "q": "alice"}, headers=pm).json()
    assert filtered["counts"] == unfiltered["counts"]
    assert filtered["total"] == 1


def test_search_and_pagination_are_pm_only(client, auth_header):
    emp_header = auth_header("emp-review@x.com", role=UserRole.employee)
    res = client.get(REVIEW, params={"date": DAY, "q": "x"}, headers=emp_header)
    assert res.status_code == 403
