"""Company Calendar event tests — focuses on the category set added in 0042
(holiday / cdc_holiday / natural_hazard / working_day) round-tripping through
the create + list API, and event_type filtering."""
from app.modules.users.models import UserRole

BASE = "/api/v1/calendar-events"


def _pm_header(auth_header):
    return auth_header("pm@example.com", role=UserRole.project_manager)


def test_create_and_list_every_category(client, auth_header):
    headers = _pm_header(auth_header)
    cases = [
        ("2026-08-15", "Independence Day", "holiday"),
        ("2026-09-01", "Founders Day", "cdc_holiday"),
        ("2026-11-20", "Cyclone closure", "natural_hazard"),
        ("2026-11-22", "Deadline working Sunday", "working_day"),
    ]
    for event_date, title, event_type in cases:
        res = client.post(
            BASE,
            json={"event_date": event_date, "title": title, "event_type": event_type},
            headers=headers,
        )
        assert res.status_code == 201, res.text
        assert res.json()["event_type"] == event_type

    listed = client.get(f"{BASE}?from=2026-01-01&to=2026-12-31", headers=headers)
    assert listed.status_code == 200, listed.text
    types = {item["event_type"] for item in listed.json()["items"]}
    assert types == {"holiday", "cdc_holiday", "natural_hazard", "working_day"}


def test_filter_by_event_type(client, auth_header):
    headers = _pm_header(auth_header)
    client.post(
        BASE,
        json={"event_date": "2026-11-22", "title": "Working Sunday", "event_type": "working_day"},
        headers=headers,
    )
    client.post(
        BASE,
        json={"event_date": "2026-08-15", "title": "Holiday", "event_type": "holiday"},
        headers=headers,
    )

    res = client.get(f"{BASE}?event_type=working_day", headers=headers)
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Working Sunday"
