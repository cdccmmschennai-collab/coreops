"""Tests for the four Phase 4C permission duration options.

Phase 4C replaced the plain "1 Hour" / "2 Hours" duration choice with four
period options; per the product's own follow-up instruction there is no plain
"1 Hour" option at all any more - every permission names a half. These tests
pin that the selected option survives form submission -> database/API ->
detail unchanged, that `duration_hours` is correctly derived from it, and that
a request written before this phase (no `period` on record) still displays.

    docker exec wms-backend-1 pytest tests/test_permission_period.py
"""
from datetime import date

import pytest

from app.modules.permissions.models import (
    PERIOD_HOURS,
    PERIOD_LABELS,
    PermissionPeriod,
    PermissionRequest,
    PermissionStatus,
    duration_label,
)
from app.modules.users.models import UserRole

API = "/api/v1/permission-requests"
# A working Monday far enough out that its month never closes.
DAY = date(2027, 3, 1)


@pytest.fixture()
def team(make_user, make_employee):
    mu = make_user("pp-mgr@x.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="PPMGR", user_id=mu.id)
    eu = make_user("pp-emp@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="PPEMP", user_id=eu.id, manager_id=mgr.id)
    return {"manager": mgr, "employee": emp}


@pytest.mark.parametrize(
    "period,expected_hours",
    [
        ("first_half_1h", 1),
        ("second_half_1h", 1),
        ("first_half_2h", 2),
        ("second_half_2h", 2),
    ],
)
def test_each_of_the_four_options_can_be_submitted_and_derives_its_hours(
    client, login, team, period, expected_hours,
):
    res = client.post(API, headers=login("pp-emp@x.com"), json={
        "permission_date": DAY.isoformat(), "period": period, "reason": "x",
    })
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["period"] == period
    assert body["duration_hours"] == expected_hours


def test_only_the_four_options_exist(client, login, team):
    """There is no plain "1 Hour" / "2 Hours" choice - a value naming just the
    hour count, without a half, must be refused."""
    for bad in ("1h", "2h", "1", "2", "1_hour", "2_hours"):
        res = client.post(API, headers=login("pp-emp@x.com"), json={
            "permission_date": DAY.isoformat(), "period": bad, "reason": "x",
        })
        assert res.status_code == 422, f"{bad}: {res.text}"


def test_the_selected_option_survives_to_the_detail_page(client, login, team):
    res = client.post(API, headers=login("pp-emp@x.com"), json={
        "permission_date": DAY.isoformat(), "period": "second_half_1h", "reason": "x",
    })
    assert res.status_code == 201, res.text
    req_id = res.json()["id"]

    detail = client.get(f"{API}/{req_id}", headers=login("pp-emp@x.com"))
    assert detail.status_code == 200, detail.text
    assert detail.json()["period"] == "second_half_1h"
    assert detail.json()["duration_hours"] == 1


def test_a_pre_phase_4c_request_with_no_period_still_displays(db, client, login, team):
    """A row written before this phase has `period = NULL`. It must keep
    reading correctly rather than 500 or invent a half."""
    req = PermissionRequest(
        employee_id=team["employee"].id, permission_date=DAY, duration_hours=2,
        period=None, status=PermissionStatus.pending,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    detail = client.get(f"{API}/{req.id}", headers=login("pp-emp@x.com"))
    assert detail.status_code == 200, detail.text
    assert detail.json()["period"] is None
    assert detail.json()["duration_hours"] == 2


def test_every_period_maps_to_exactly_one_hour_count():
    assert PERIOD_HOURS == {
        PermissionPeriod.first_half_1h: 1,
        PermissionPeriod.second_half_1h: 1,
        PermissionPeriod.first_half_2h: 2,
        PermissionPeriod.second_half_2h: 2,
    }


def test_every_period_has_the_exact_label():
    assert PERIOD_LABELS == {
        PermissionPeriod.first_half_1h: "1st Half — 1 Hour",
        PermissionPeriod.second_half_1h: "2nd Half — 1 Hour",
        PermissionPeriod.first_half_2h: "1st Half — 2 Hours",
        PermissionPeriod.second_half_2h: "2nd Half — 2 Hours",
    }


def test_duration_label_never_collapses_a_half_into_the_plain_hour_count():
    assert duration_label(1, PermissionPeriod.first_half_1h) == "1st Half — 1 Hour"
    assert duration_label(2, PermissionPeriod.second_half_2h) == "2nd Half — 2 Hours"


def test_duration_label_falls_back_to_the_plain_form_only_without_a_period():
    assert duration_label(1, None) == "1 hour"
    assert duration_label(2, None) == "2 hours"
