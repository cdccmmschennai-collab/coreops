"""Phase 6 - daily biometric summary: first IN / last OUT (no migration).

Two layers:
  * the pure boundary rule in `summary.py` (no DB)
  * the endpoint, DB-backed, over the real edge cases: missing OUT, missing IN,
    multiple IN/OUT pairs, duplicate punches, out-of-order punches, and unmapped
    employees.

The invariants that must never break: no punch is rewritten, no attendance
record is created, and nobody sees another employee's summary.
"""
import uuid
from datetime import datetime, timedelta, timezone
from datetime import time as dtime

import pytest
from sqlalchemy import Text, cast, func, select

from app.modules.attendance.models import AttendanceRecord
from app.modules.biometric.constants import DERIVATION_ANCHOR
from app.modules.biometric.models import BiometricEmployeeMapping, BiometricPunch
from app.modules.biometric.summary import (
    DEDUP_WINDOW_SECONDS,
    collapse_rescans,
    summarize_day,
)
from app.modules.users.models import UserRole

SUMMARY = "/api/v1/biometric/daily-summary"

# 2026-07-29 in IST. 03:30Z is 09:00 IST - the real arrival peak in the backfill.
IST_OFFSET = timedelta(hours=5, minutes=30)


def ist(y: int, m: int, d: int, hh: int, mm: int, ss: int = 0) -> datetime:
    """An Asia/Kolkata wall-clock instant, stored as aware UTC."""
    return datetime(y, m, d, hh, mm, ss, tzinfo=timezone(IST_OFFSET))


@pytest.fixture()
def pm(auth_header):
    return auth_header("pm@x.com", role=UserRole.project_manager)


@pytest.fixture()
def punch(db):
    counter = {"n": 0}

    def _make(code: str, when: datetime, *, provider: str = "easytime") -> BiometricPunch:
        counter["n"] += 1
        row = BiometricPunch(
            provider=provider,
            external_transaction_id=f"txn-{counter['n']}",
            external_employee_code=code,
            employee_id=None,  # as the real backfill is: attribution via mapping
            punch_time=when,
            received_at=datetime.now(timezone.utc),
            raw_punch_state="0",  # the only value EasyTime ever sent
        )
        db.add(row)
        db.commit()
        return row

    return _make


@pytest.fixture()
def mapping(db):
    def _make(code: str, employee_id: uuid.UUID) -> BiometricEmployeeMapping:
        row = BiometricEmployeeMapping(
            provider="easytime",
            external_employee_code=code,
            employee_id=employee_id,
            is_active=True,
        )
        db.add(row)
        db.commit()
        return row

    return _make


def _summary(client, headers, *, date_from="2026-07-29", date_to="2026-07-29", **extra):
    params = {"from": date_from, "to": date_to, **extra}
    res = client.get(SUMMARY, params=params, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _by_date(payload) -> dict:
    return {i["summary_date"]: i for i in payload["items"]}


# ── the pure rule ───────────────────────────────────────────────────────────

def test_empty_day_summarizes_to_nothing():
    s = summarize_day([])
    assert s.first_in is None and s.last_out is None
    assert s.punch_count == 0 and s.kept_count == 0


def test_boundary_is_earliest_and_latest():
    times = [ist(2026, 7, 29, 9, 0), ist(2026, 7, 29, 13, 5), ist(2026, 7, 29, 18, 30)]
    s = summarize_day(times)
    assert s.first_in == times[0]
    assert s.last_out == times[2]
    assert s.punch_count == 3


def test_out_of_order_input_is_sorted_not_trusted():
    early = ist(2026, 7, 29, 9, 0)
    late = ist(2026, 7, 29, 18, 30)
    # A backfill can hand us the later punch first.
    s = summarize_day([late, early])
    assert s.first_in == early
    assert s.last_out == late


def test_a_single_punch_never_invents_an_out():
    only = ist(2026, 7, 29, 11, 34)  # real: code 1002 on 2026-08-10
    s = summarize_day([only])
    assert s.first_in == only
    assert s.last_out is None
    assert s.kept_count == 1


def test_rescan_burst_collapses_to_one_punch():
    # Real data: code 187 tapped at 10:43:20 / :28 / :34 on 2026-08-11.
    burst = [
        ist(2026, 8, 11, 10, 43, 20),
        ist(2026, 8, 11, 10, 43, 28),
        ist(2026, 8, 11, 10, 43, 34),
    ]
    assert collapse_rescans(burst) == [burst[0]]
    s = summarize_day(burst)
    # Three raw punches, one real event - so still no OUT.
    assert s.punch_count == 3
    assert s.kept_count == 1
    assert s.last_out is None


def test_a_long_burst_does_not_ratchet_the_window_forward():
    # Comparing against the last KEPT punch (not the previous raw one) is what
    # keeps a slow drip of taps from surviving one-by-one.
    base = ist(2026, 7, 29, 9, 0)
    drip = [base + timedelta(seconds=20 * i) for i in range(4)]  # 0,20,40,60
    kept = collapse_rescans(drip)
    assert kept == [drip[0], drip[3]]  # only the one a full window later


def test_identical_timestamps_are_collapsed():
    t = ist(2026, 7, 29, 9, 0)
    s = summarize_day([t, t, t])
    assert s.kept_count == 1
    assert s.last_out is None


def test_a_punch_exactly_one_window_later_is_kept():
    a = ist(2026, 7, 29, 9, 0)
    b = a + timedelta(seconds=DEDUP_WINDOW_SECONDS)
    assert collapse_rescans([a, b]) == [a, b]


def test_collapse_does_not_mutate_its_input():
    times = [ist(2026, 7, 29, 18, 0), ist(2026, 7, 29, 9, 0)]
    snapshot = list(times)
    collapse_rescans(times)
    assert times == snapshot


# ── the endpoint over real shapes ───────────────────────────────────────────

def test_normal_day_reports_first_in_and_last_out(client, pm, punch, mapping, make_employee):
    emp = make_employee(employee_code="EMP061", first_name="Asha", last_name="Rao")
    mapping("61", emp.id)
    punch("61", ist(2026, 7, 29, 9, 19))
    punch("61", ist(2026, 7, 29, 13, 5))
    punch("61", ist(2026, 7, 29, 18, 3))

    row = _summary(client, pm)["items"][0]
    assert row["employee_code"] == "EMP061"
    assert row["employee_name"] == "Asha Rao"
    assert row["summary_date"] == "2026-07-29"
    assert row["first_in"].startswith("2026-07-29T03:49")   # 09:19 IST
    assert row["last_out"].startswith("2026-07-29T12:33")   # 18:03 IST
    assert row["punch_count"] == 3


def test_multiple_in_out_pairs_collapse_to_the_outer_boundary(
    client, pm, punch, mapping, make_employee
):
    # Real shape: code 1001 punched 9 times on 2026-07-29 (lunch trips).
    emp = make_employee(employee_code="EMP001")
    mapping("1001", emp.id)
    for hh, mm in [(4, 25), (4, 59), (6, 26), (6, 54), (7, 16), (7, 59), (8, 20), (18, 27), (20, 8)]:
        punch("1001", ist(2026, 7, 29, hh, mm))

    row = _summary(client, pm)["items"][0]
    assert row["punch_count"] == 9
    assert row["first_in"].startswith("2026-07-28T22:55")  # 04:25 IST next day
    assert row["last_out"].startswith("2026-07-29T14:38")  # 20:08 IST
    # No pairing, no session count - just the boundary.
    assert "sessions" not in row and "total_minutes" not in row


def test_missing_out_reports_first_in_only(client, pm, punch, mapping, make_employee):
    emp = make_employee(employee_code="EMP002")
    mapping("1002", emp.id)
    punch("1002", ist(2026, 7, 29, 11, 34))

    row = _summary(client, pm)["items"][0]
    assert row["first_in"] is not None
    assert row["last_out"] is None


def test_missing_in_is_not_a_thing_but_a_late_only_punch_still_reports(
    client, pm, punch, mapping, make_employee
):
    """A person seen only at going-home time.

    There is no way to know an earlier IN was missed - the device recorded one
    sighting. It becomes first_in with no last_out rather than being guessed into
    an OUT, which would silently invent an arrival of "unknown".
    """
    emp = make_employee(employee_code="EMP003")
    mapping("1003", emp.id)
    punch("1003", ist(2026, 8, 11, 18, 28))

    row = _summary(client, pm, date_from="2026-08-11", date_to="2026-08-11")["items"][0]
    assert row["first_in"].startswith("2026-08-11T12:58")
    assert row["last_out"] is None
    assert row["kept_count"] == 1


def test_duplicate_punches_do_not_create_a_false_out(
    client, pm, punch, mapping, make_employee
):
    emp = make_employee(employee_code="EMP004")
    mapping("1004", emp.id)
    punch("1004", ist(2026, 7, 29, 9, 15, 10))
    punch("1004", ist(2026, 7, 29, 9, 15, 18))  # same tap, second read

    row = _summary(client, pm)["items"][0]
    assert row["punch_count"] == 2
    assert row["kept_count"] == 1
    assert row["last_out"] is None


def test_out_of_order_stored_punches_still_bound_the_day(
    client, pm, punch, mapping, make_employee
):
    emp = make_employee(employee_code="EMP005")
    mapping("1005", emp.id)
    # Inserted late-first, as a backfill would.
    punch("1005", ist(2026, 7, 29, 18, 45))
    punch("1005", ist(2026, 7, 29, 9, 2))

    row = _summary(client, pm)["items"][0]
    assert row["first_in"].startswith("2026-07-29T03:32")  # 09:02 IST
    assert row["last_out"].startswith("2026-07-29T13:15")  # 18:45 IST


def test_unmapped_code_is_absent_from_the_summary(client, pm, punch, make_employee):
    make_employee(employee_code="EMP061")  # exists, but NO mapping row
    punch("61", ist(2026, 7, 29, 9, 19))
    punch("61", ist(2026, 7, 29, 18, 3))

    assert _summary(client, pm)["items"] == []


def test_mapping_created_today_covers_punches_stored_earlier(
    client, pm, punch, mapping, make_employee, db
):
    """The reason attribution joins the mapping table instead of punch.employee_id.

    Every punch in the real backfill was stored with employee_id NULL, before any
    mapping existed. Reading the stored column would report an empty calendar
    forever.
    """
    emp = make_employee(employee_code="EMP069")
    punch("69", ist(2026, 7, 29, 9, 8))
    punch("69", ist(2026, 7, 29, 19, 19))
    assert _summary(client, pm)["items"] == []

    mapping("69", emp.id)  # mapped only now
    row = _summary(client, pm)["items"][0]
    assert row["first_in"] is not None and row["last_out"] is not None
    # And the punches themselves were never touched.
    assert db.execute(
        select(func.count()).select_from(BiometricPunch).where(
            BiometricPunch.employee_id.isnot(None)
        )
    ).scalar_one() == 0


def test_two_codes_for_one_employee_merge_into_one_day(
    client, pm, punch, mapping, make_employee
):
    emp = make_employee(employee_code="EMP007")
    mapping("7", emp.id)
    mapping("1007", emp.id)
    punch("7", ist(2026, 7, 29, 9, 5))
    punch("1007", ist(2026, 7, 29, 18, 40))

    items = _summary(client, pm)["items"]
    assert len(items) == 1
    assert items[0]["external_employee_codes"] == ["1007", "7"]
    assert items[0]["first_in"].startswith("2026-07-29T03:35")
    assert items[0]["last_out"].startswith("2026-07-29T13:10")


# ── attendance-day semantics ────────────────────────────────────────────────

def test_days_are_bucketed_in_ist_not_utc(client, pm, punch, mapping, make_employee):
    """A 01:00 IST punch belongs to the IST day, not the previous UTC day."""
    emp = make_employee(employee_code="EMP008")
    mapping("1008", emp.id)
    # 2026-07-29 01:00 IST == 2026-07-28 19:30 UTC.
    punch("1008", ist(2026, 7, 29, 1, 0))
    punch("1008", ist(2026, 7, 29, 2, 0))

    by_date = _by_date(_summary(client, pm, date_from="2026-07-28", date_to="2026-07-29"))
    assert "2026-07-29" in by_date
    assert "2026-07-28" not in by_date


def test_each_day_is_summarized_separately(client, pm, punch, mapping, make_employee):
    emp = make_employee(employee_code="EMP009")
    mapping("1009", emp.id)
    punch("1009", ist(2026, 7, 29, 9, 0))
    punch("1009", ist(2026, 7, 29, 18, 0))
    punch("1009", ist(2026, 7, 30, 9, 30))

    by_date = _by_date(_summary(client, pm, date_from="2026-07-29", date_to="2026-07-30"))
    assert by_date["2026-07-29"]["last_out"] is not None
    # A lone punch the next day does not borrow the previous day's OUT.
    assert by_date["2026-07-30"]["last_out"] is None


def test_a_punch_outside_the_range_is_excluded(client, pm, punch, mapping, make_employee):
    emp = make_employee(employee_code="EMP010")
    mapping("1010", emp.id)
    punch("1010", ist(2026, 7, 28, 9, 0))
    punch("1010", ist(2026, 7, 29, 9, 0))
    punch("1010", ist(2026, 7, 29, 18, 0))

    items = _summary(client, pm)["items"]
    assert len(items) == 1
    assert items[0]["summary_date"] == "2026-07-29"


def test_other_providers_are_not_summarized(client, pm, punch, mapping, make_employee):
    emp = make_employee(employee_code="EMP011")
    mapping("1011", emp.id)
    punch("1011", ist(2026, 7, 29, 9, 0), provider="other")
    punch("1011", ist(2026, 7, 29, 18, 0), provider="other")

    assert _summary(client, pm)["items"] == []


# ── Phase 6A: what the human reviewer is shown ──────────────────────────────

def test_surviving_punch_times_are_returned_for_review(
    client, pm, punch, mapping, make_employee
):
    """The boundary is derived, so a reviewer must see what it was derived FROM."""
    emp = make_employee(employee_code="EMP020")
    mapping("1020", emp.id)
    punch("1020", ist(2026, 7, 29, 9, 5))
    punch("1020", ist(2026, 7, 29, 13, 30))
    punch("1020", ist(2026, 7, 29, 18, 10))

    row = _summary(client, pm)["items"][0]
    assert len(row["punch_times"]) == 3
    # Chronological, and the boundary is the first and last of exactly this list.
    assert row["punch_times"] == sorted(row["punch_times"])
    assert row["punch_times"][0] == row["first_in"]
    assert row["punch_times"][-1] == row["last_out"]


def test_collapsed_rescans_are_absent_from_the_review_list(
    client, pm, punch, mapping, make_employee
):
    emp = make_employee(employee_code="EMP021")
    mapping("1021", emp.id)
    punch("1021", ist(2026, 7, 29, 9, 5, 0))
    punch("1021", ist(2026, 7, 29, 9, 5, 8))   # re-scan, collapsed
    punch("1021", ist(2026, 7, 29, 18, 10))

    row = _summary(client, pm)["items"][0]
    assert row["punch_count"] == 3
    assert len(row["punch_times"]) == 2  # what a reviewer should actually see
    assert row["kept_count"] == 2


def test_punch_times_never_leak_the_raw_payload(client, pm, punch, mapping, make_employee):
    emp = make_employee(employee_code="EMP022")
    mapping("1022", emp.id)
    punch("1022", ist(2026, 7, 29, 9, 5))

    row = _summary(client, pm)["items"][0]
    assert row["punch_times"] == [row["first_in"]]
    for leaked in ("raw_payload", "terminal_serial_number", "external_transaction_id"):
        assert leaked not in row


def test_the_office_schedule_is_returned_for_a_single_employee(
    client, pm, punch, mapping, make_employee, db
):
    """CoreOps' own contracted hours, so a reviewer can compare against them."""
    from app.modules.offices.models import Office

    office = Office(
        name="Chennai Test",
        timezone="Asia/Kolkata",
        shift_start=dtime(9, 30),
        shift_end=dtime(17, 30),
        break_minutes=30,
    )
    db.add(office)
    db.commit()

    emp = make_employee(employee_code="EMP023")
    emp.office_id = office.id
    db.add(emp)
    db.commit()
    mapping("1023", emp.id)
    punch("1023", ist(2026, 7, 29, 9, 10))

    payload = _summary(client, pm, employee_id=str(emp.id))
    assert payload["schedule"]["shift_start"] == "09:30:00"
    assert payload["schedule"]["shift_end"] == "17:30:00"
    assert payload["schedule"]["break_minutes"] == 30
    assert payload["schedule"]["office_name"] == "Chennai Test"


def test_the_schedule_is_available_on_a_day_with_no_punches(
    client, pm, mapping, make_employee, db
):
    """A no-punch day still has to show CoreOps Time - there is no item to
    hang it on, which is why the schedule sits on the page."""
    from app.modules.offices.models import Office

    office = Office(
        name="Chennai Empty",
        timezone="Asia/Kolkata",
        shift_start=dtime(9, 0),
        shift_end=dtime(17, 30),
        break_minutes=30,
    )
    db.add(office)
    db.commit()

    emp = make_employee(employee_code="EMP024")
    emp.office_id = office.id
    db.add(emp)
    db.commit()

    payload = _summary(client, pm, employee_id=str(emp.id))
    assert payload["items"] == []          # no biometric record
    assert payload["schedule"] is not None  # but the expected window is known
    assert payload["schedule"]["shift_start"] == "09:00:00"


def test_no_schedule_is_not_an_error(client, pm, punch, mapping, make_employee):
    """`employees.office_id` is nullable - a missing schedule is normal."""
    emp = make_employee(employee_code="EMP025")  # no office
    mapping("1025", emp.id)
    punch("1025", ist(2026, 7, 29, 9, 10))

    payload = _summary(client, pm, employee_id=str(emp.id))
    assert payload["schedule"] is None
    assert payload["items"][0]["first_in"] is not None


def test_no_schedule_is_returned_when_every_employee_is_in_scope(
    client, pm, punch, mapping, make_employee, db
):
    """Without a single employee in scope there is no one schedule to report."""
    from app.modules.offices.models import Office

    office = Office(
        name="Chennai Many",
        timezone="Asia/Kolkata",
        shift_start=dtime(9, 0),
        shift_end=dtime(17, 30),
        break_minutes=30,
    )
    db.add(office)
    db.commit()
    emp = make_employee(employee_code="EMP026")
    emp.office_id = office.id
    db.add(emp)
    db.commit()
    mapping("1026", emp.id)
    punch("1026", ist(2026, 7, 29, 9, 10))

    assert _summary(client, pm)["schedule"] is None  # no employee_id filter


# ── contract, scope and the shadow guarantee ────────────────────────────────

def test_response_declares_how_the_boundary_was_derived(
    client, pm, punch, mapping, make_employee
):
    emp = make_employee(employee_code="EMP012")
    mapping("1012", emp.id)
    punch("1012", ist(2026, 7, 29, 9, 0))

    payload = _summary(client, pm)
    assert payload["derivation"] == DERIVATION_ANCHOR
    # EasyTime sends no usable direction, and the API says so rather than
    # implying these are device-reported IN/OUT states.
    assert payload["punch_state_available"] is False
    assert payload["provider"] == "easytime"


def test_an_employee_sees_their_own_summary(
    client, login, make_user, punch, mapping, make_employee
):
    user = make_user("self@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="EMP013", user_id=user.id)
    mapping("1013", emp.id)
    punch("1013", ist(2026, 7, 29, 9, 0))
    punch("1013", ist(2026, 7, 29, 18, 0))

    items = _summary(client, login("self@x.com"))["items"]
    assert len(items) == 1
    assert items[0]["employee_code"] == "EMP013"
    assert items[0]["last_out"] is not None


def test_an_employee_sees_only_their_own_row_in_an_unfiltered_read(
    client, login, make_user, punch, mapping, make_employee
):
    user = make_user("mine@x.com", role=UserRole.employee)
    mine = make_employee(employee_code="EMP017", user_id=user.id)
    theirs = make_employee(employee_code="EMP018")
    mapping("1017", mine.id)
    mapping("1018", theirs.id)
    for code in ("1017", "1018"):
        punch(code, ist(2026, 7, 29, 9, 0))
        punch(code, ist(2026, 7, 29, 18, 0))

    items = _summary(client, login("mine@x.com"))["items"]
    assert [i["employee_code"] for i in items] == ["EMP017"]


def test_an_employee_cannot_read_someone_elses_summary(
    client, login, make_user, punch, mapping, make_employee
):
    other = make_employee(employee_code="EMP014")
    mapping("1014", other.id)
    punch("1014", ist(2026, 7, 29, 9, 0))

    nosy_user = make_user("nosy@x.com", role=UserRole.employee)
    make_employee(employee_code="EMP014B", user_id=nosy_user.id)
    headers = login("nosy@x.com")
    res = client.get(
        SUMMARY,
        params={"from": "2026-07-29", "to": "2026-07-29", "employee_id": str(other.id)},
        headers=headers,
    )
    assert res.status_code == 403


def test_a_user_with_no_employee_profile_sees_nothing(
    client, auth_header, punch, mapping, make_employee
):
    emp = make_employee(employee_code="EMP015")
    mapping("1015", emp.id)
    punch("1015", ist(2026, 7, 29, 9, 0))

    headers = auth_header("ghost@x.com", role=UserRole.employee)
    assert _summary(client, headers)["items"] == []


def test_summary_requires_auth(client):
    res = client.get(SUMMARY, params={"from": "2026-07-29", "to": "2026-07-29"})
    assert res.status_code == 401


def test_a_reversed_range_is_rejected(client, pm):
    res = client.get(
        SUMMARY, params={"from": "2026-07-29", "to": "2026-07-01"}, headers=pm
    )
    assert res.status_code == 422


def test_an_oversized_range_is_rejected(client, pm):
    res = client.get(
        SUMMARY, params={"from": "2026-01-01", "to": "2026-12-31"}, headers=pm
    )
    assert res.status_code == 422


def test_an_unsupported_provider_is_rejected(client, pm):
    res = client.get(
        SUMMARY,
        params={"from": "2026-07-29", "to": "2026-07-29", "provider": "nope"},
        headers=pm,
    )
    assert res.status_code == 422


def test_the_summary_writes_nothing_at_all(client, pm, punch, mapping, make_employee, db):
    """The shadow guarantee: no punch mutated, no attendance record created."""
    emp = make_employee(employee_code="EMP016")
    mapping("1016", emp.id)
    punch("1016", ist(2026, 7, 29, 9, 0))
    punch("1016", ist(2026, 7, 29, 18, 0))

    fingerprint = select(
        func.md5(func.string_agg(cast(BiometricPunch.id, Text), ","))
    )
    before = db.execute(fingerprint).scalar_one()

    _summary(client, pm)
    _summary(client, pm)

    assert db.execute(fingerprint).scalar_one() == before
    # Phase 6 derives no attendance.
    assert db.execute(
        select(func.count()).select_from(AttendanceRecord)
    ).scalar_one() == 0
    assert db.execute(
        select(func.count()).select_from(BiometricPunch).where(
            BiometricPunch.employee_id.isnot(None)
        )
    ).scalar_one() == 0
