"""Phase 7 - worked duration + attendance classification (no migration).

Three layers:
  * the pure engine in `classification.py` (no DB): duration, the scheduled
    window, and the verdict for every shape the data can take;
  * the endpoint, DB-backed, over the real office shift configuration;
  * the guarantees: nothing is written, and no CAUSE is ever concluded.

The invariants that must never break: a single punch never becomes a full day, a
short day never becomes a half day, a no-punch day never becomes an absence, and
`attendance_records` is not touched.
"""
import uuid
from datetime import datetime, timedelta, timezone
from datetime import date as ddate
from datetime import time as dtime

import pytest
from sqlalchemy import Text, cast, func, select

from app.modules.attendance.models import AttendanceRecord
from app.modules.biometric.classification import (
    Shift,
    classify_day,
    scheduled_window,
    worked_minutes,
)
from app.modules.biometric.constants import (
    CLASSIFICATION_INCOMPLETE,
    CLASSIFICATION_NEEDS_REVIEW,
    CLASSIFICATION_NO_RECORD,
    CLASSIFICATION_PRESENT,
    CLASSIFICATIONS,
    DEFAULT_SHIFT_END,
    DEFAULT_SHIFT_START,
    REASON_DEFAULT_SHIFT_ASSUMED,
    REASON_EARLY_LAST_PUNCH,
    REASON_LATE_FIRST_PUNCH,
    REASON_MISSING_SECOND_PUNCH,
    REASON_NO_BIOMETRIC_RECORD,
    REASON_SHIFT_TIMEZONE_INVALID,
    REASON_SHIFT_UNKNOWN,
    REASON_SHORT_OF_SCHEDULED,
    REASON_UNSUPPORTED_SHIFT_WINDOW,
    SHIFT_SOURCE_DEFAULT,
    SHIFT_SOURCE_OFFICE,
    SHORTFALL_GRACE_MINUTES,
)
from app.modules.biometric.models import BiometricEmployeeMapping, BiometricPunch
from app.modules.biometric.summary import EMPTY_DAY, summarize_day
from app.modules.offices.models import Office
from app.modules.users.models import UserRole

SUMMARY = "/api/v1/biometric/daily-summary"

IST_OFFSET = timedelta(hours=5, minutes=30)
DAY = ddate(2026, 7, 29)

# The confirmed CoreOps office window: 09:00 -> 17:30 Asia/Kolkata = 510 minutes.
# Taken from the constants, not retyped, so a change to the fallback cannot leave
# these tests asserting a number the code no longer uses.
CHENNAI = Shift(
    start=DEFAULT_SHIFT_START,
    end=DEFAULT_SHIFT_END,
    timezone="Asia/Kolkata",
    break_minutes=30,
    source=SHIFT_SOURCE_OFFICE,
)
SCHEDULED_MINUTES = 510


def ist(hh: int, mm: int, ss: int = 0, *, day: ddate = DAY) -> datetime:
    """An Asia/Kolkata wall-clock instant on `day`, as aware UTC."""
    return datetime(
        day.year, day.month, day.day, hh, mm, ss, tzinfo=timezone(IST_OFFSET)
    )


def verdict(*times: datetime, shift: Shift | None = CHENNAI, day: ddate = DAY):
    """Classify a day straight from its punch instants, via the Phase 6 rule."""
    return classify_day(summarize_day(times), day=day, shift=shift)


# ── the scheduled window ────────────────────────────────────────────────────

def test_the_office_window_is_eight_and_a_half_hours():
    """09:00 -> 17:30 is a START and an END. It is 510 minutes of elapsed window,
    not a "required 8h 30m" - the required duration (O-1) is still open."""
    start_at, end_at, minutes, problem = scheduled_window(DAY, CHENNAI)
    assert minutes == SCHEDULED_MINUTES
    assert problem is None
    # Built in the office's own timezone, returned as UTC like every other
    # timestamp in the API.
    assert start_at == ist(9, 0)
    assert end_at == ist(17, 30)
    assert start_at.utcoffset() == timedelta(0)


def test_a_missing_shift_is_reported_not_assumed():
    assert scheduled_window(DAY, None) == (None, None, None, REASON_SHIFT_UNKNOWN)


def test_a_broken_office_timezone_refuses_rather_than_falling_back_to_utc():
    """Reading a contracted 09:00 as UTC would move it by 5h30m for every day."""
    broken = Shift(dtime(9, 0), dtime(17, 30), "Mars/Olympus", source=SHIFT_SOURCE_OFFICE)
    assert scheduled_window(DAY, broken)[3] == REASON_SHIFT_TIMEZONE_INVALID


def test_a_night_shift_window_is_refused_not_wrapped_to_the_next_day():
    """Cross-midnight shifts are explicitly out of scope for Phase 7."""
    night = Shift(dtime(22, 0), dtime(6, 0), "Asia/Kolkata")
    assert scheduled_window(DAY, night)[3] == REASON_UNSUPPORTED_SHIFT_WINDOW


def test_a_zero_length_window_is_refused():
    same = Shift(dtime(9, 0), dtime(9, 0), "Asia/Kolkata")
    assert scheduled_window(DAY, same)[3] == REASON_UNSUPPORTED_SHIFT_WINDOW


def test_a_longer_office_window_is_honoured_verbatim():
    """The Qatar row is 09:00 - 18:00. Nothing normalizes it to Chennai's."""
    qatar = Shift(dtime(9, 0), dtime(18, 0), "Asia/Qatar", break_minutes=60)
    assert scheduled_window(DAY, qatar)[2] == 540


# ── worked duration ─────────────────────────────────────────────────────────

def test_duration_is_elapsed_time_between_the_two_boundaries():
    assert worked_minutes(ist(9, 10), ist(17, 10)) == 480


def test_duration_is_null_not_zero_without_both_boundaries():
    """Zero would read as "was here for no time" - a measurement. Null is the
    truth: not measurable from this evidence."""
    assert worked_minutes(ist(9, 10), None) is None
    assert worked_minutes(None, ist(17, 10)) is None
    assert worked_minutes(None, None) is None


def test_duration_truncates_rather_than_rounding_up():
    """A reported duration must never exceed the time actually observed."""
    assert worked_minutes(ist(9, 0, 0), ist(9, 1, 59)) == 1


def test_a_negative_span_is_refused_rather_than_shown_as_zero():
    assert worked_minutes(ist(17, 10), ist(9, 10)) is None


def test_the_break_is_never_deducted():
    """O-2 (does the lunch count as worked time?) is open, so 30 minutes are not
    quietly removed from every day."""
    assert CHENNAI.break_minutes == 30
    assert verdict(ist(9, 0), ist(17, 30)).worked_minutes == SCHEDULED_MINUTES


# ── the required cases, one test each ───────────────────────────────────────

def test_1_a_full_scheduled_day_is_objectively_present():
    v = verdict(ist(9, 0), ist(17, 30))
    assert v.worked_minutes == 510
    assert v.scheduled_minutes == 510
    assert v.classification == CLASSIFICATION_PRESENT
    assert v.review_required is False
    assert v.reasons == ()


def test_2_a_slightly_late_arrival_is_complete_and_never_a_half_day():
    v = verdict(ist(9, 10), ist(17, 30))
    assert v.worked_minutes == 500  # 8h 20m
    # Both punches exist, so the day is complete evidence and settled.
    assert v.classification == CLASSIFICATION_PRESENT
    assert v.review_required is False
    # The shortfall is still REPORTED - it just no longer demands attention.
    assert REASON_SHORT_OF_SCHEDULED in v.reasons
    assert REASON_LATE_FIRST_PUNCH in v.reasons
    # And a cause is still never invented from a duration.
    assert "half_day" not in v.reasons and "permission" not in v.reasons


def test_3_a_slightly_early_departure_is_complete_and_never_a_half_day():
    v = verdict(ist(9, 0), ist(17, 20))
    assert v.worked_minutes == 500  # 8h 20m
    assert v.classification == CLASSIFICATION_PRESENT
    assert v.review_required is False
    assert REASON_EARLY_LAST_PUNCH in v.reasons
    assert REASON_LATE_FIRST_PUNCH not in v.reasons


def test_4_eight_hours_against_a_scheduled_eight_and_a_half_is_settled():
    """THE RULE CHANGE (2026-08-14): completeness settles a day, not duration.

    Under Phase 7 this was `needs_review`. On real data that flagged four people
    for being ~12 minutes short, which is noise. Two punches means the device saw
    the whole day, so there is nothing a human can add.
    """
    v = verdict(ist(9, 10), ist(17, 10))
    assert v.worked_minutes == 480
    assert v.scheduled_minutes == 510
    assert v.classification == CLASSIFICATION_PRESENT
    assert v.review_required is False
    assert REASON_SHORT_OF_SCHEDULED in v.reasons  # reported, not blocking


def test_5_a_single_punch_is_incomplete_and_invents_no_out():
    v = verdict(ist(9, 10))
    assert v.first_in == ist(9, 10)
    assert v.last_out is None
    assert v.worked_minutes is None
    assert v.classification == CLASSIFICATION_INCOMPLETE
    assert v.review_required is True
    assert v.reasons[0] == REASON_MISSING_SECOND_PUNCH
    # Specifically NOT the shift end.
    assert v.last_out != v.scheduled_end_at


def test_6_a_single_afternoon_punch_is_incomplete_not_a_half_day():
    v = verdict(ist(13, 0))
    assert v.first_in == ist(13, 0)
    assert v.last_out is None
    assert v.classification == CLASSIFICATION_INCOMPLETE
    assert v.review_required is True
    # Late, and that is recorded - but it is not a conclusion about why.
    assert REASON_LATE_FIRST_PUNCH in v.reasons


def test_7_no_punch_is_unresolved_and_never_absent():
    v = classify_day(EMPTY_DAY, day=DAY, shift=CHENNAI)
    assert v.classification == CLASSIFICATION_NO_RECORD
    assert v.classification != "absent"
    assert v.review_required is True
    assert v.reasons[0] == REASON_NO_BIOMETRIC_RECORD
    assert v.worked_minutes is None
    # The expected window is still reported, so a reviewer sees what was missed.
    assert v.scheduled_minutes == SCHEDULED_MINUTES


def test_8_middle_punches_are_not_session_boundaries():
    v = verdict(ist(9, 10), ist(12, 30), ist(13, 0), ist(17, 10))
    assert v.first_in == ist(9, 10)
    assert v.last_out == ist(17, 10)
    assert v.worked_minutes == 480  # not 480 minus the 30-minute midday gap
    assert v.classification == CLASSIFICATION_PRESENT


def test_9_rescans_are_collapsed_by_the_phase_6_rule_before_any_measurement():
    v = verdict(ist(9, 10, 0), ist(9, 10, 15), ist(9, 10, 40), ist(17, 10))
    assert v.first_in == ist(9, 10, 0)
    assert v.last_out == ist(17, 10)
    assert v.worked_minutes == 480


def test_10_out_of_order_input_is_sorted_before_measurement():
    v = verdict(ist(17, 10), ist(9, 10), ist(12, 0))
    assert v.first_in == ist(9, 10)
    assert v.last_out == ist(17, 10)
    assert v.worked_minutes == 480


def test_11_identical_timestamps_stay_one_effective_punch():
    v = verdict(ist(9, 10), ist(9, 10))
    assert v.last_out is None
    assert v.worked_minutes is None
    assert v.classification == CLASSIFICATION_INCOMPLETE


def test_12_two_punches_inside_the_dedup_window_are_one_event():
    v = verdict(ist(9, 10, 0), ist(9, 10, 20))
    assert v.last_out is None
    assert v.classification == CLASSIFICATION_INCOMPLETE


def test_13_two_punches_beyond_the_dedup_window_both_survive():
    """A two-minute day is a real (absurd) measurement and is reported as one.

    Under the completeness rule it classifies as `present` with a shortfall note,
    because two punches IS complete evidence. Worth knowing: the rule trusts the
    device, so an absurd-but-complete day is not questioned. A duration floor
    would be a separate, explicit policy decision.
    """
    v = verdict(ist(9, 10), ist(9, 12))
    assert v.last_out == ist(9, 12)
    assert v.worked_minutes == 2
    assert v.classification == CLASSIFICATION_PRESENT
    assert REASON_SHORT_OF_SCHEDULED in v.reasons


def test_14_an_afternoon_arrival_is_complete_evidence():
    """CONSEQUENCE OF THE RULE CHANGE, recorded deliberately.

    13:05 -> 17:20 is 4h 15m against a 8h 30m window and is now `present`, not
    `needs_review`, because both punches exist. If a half-day-sized shortfall
    should come back to the PM, that needs an explicit duration floor - it is not
    what the completeness rule does.
    """
    v = verdict(ist(13, 5), ist(17, 20))
    assert v.worked_minutes == 255  # 4h 15m
    assert v.classification == CLASSIFICATION_PRESENT
    assert v.review_required is False
    # Still no half day, no permission, no leave - a cause is never invented.
    assert set(v.reasons) <= {
        REASON_SHORT_OF_SCHEDULED,
        REASON_LATE_FIRST_PUNCH,
        REASON_EARLY_LAST_PUNCH,
    }


def test_15_arriving_a_minute_early_and_leaving_on_time_is_present():
    v = verdict(ist(8, 59), ist(17, 30))
    assert v.worked_minutes == 511
    assert v.classification == CLASSIFICATION_PRESENT
    assert v.review_required is False
    # More than scheduled is NOT overtime here. Phase 7 computes no overtime.
    assert not any("overtime" in r for r in v.reasons)


def test_a_late_arrival_that_stays_late_enough_is_still_a_complete_day():
    """Being late is an observation, not a verdict: 09:10 -> 17:40 is 8h 30m."""
    v = verdict(ist(9, 10), ist(17, 40))
    assert v.worked_minutes == SCHEDULED_MINUTES
    assert v.classification == CLASSIFICATION_PRESENT
    assert v.review_required is False
    assert v.reasons == (REASON_LATE_FIRST_PUNCH,)


def test_a_day_measured_against_no_shift_at_all_goes_to_review():
    v = verdict(ist(9, 0), ist(17, 30), shift=None)
    assert v.worked_minutes == 510  # still measurable
    assert v.scheduled_minutes is None  # but not comparable
    assert v.classification == CLASSIFICATION_NEEDS_REVIEW
    assert REASON_SHIFT_UNKNOWN in v.reasons
    assert v.shift_source is None


def test_the_fallback_shift_is_flagged_as_assumed():
    """An employee with no office is compared against the module default, and the
    row says so rather than presenting it as configuration."""
    v = verdict(
        ist(9, 0), ist(17, 30), shift=Shift.default(timezone_name="Asia/Kolkata")
    )
    assert v.shift_source == SHIFT_SOURCE_DEFAULT
    assert v.scheduled_minutes == SCHEDULED_MINUTES
    assert REASON_DEFAULT_SHIFT_ASSUMED in v.reasons
    # An assumed shift is context, not a review trigger on its own.
    assert v.classification == CLASSIFICATION_PRESENT
    assert v.review_required is False


def test_16_the_ist_day_boundary_uses_the_days_own_scheduled_window():
    """A 00:30 IST punch belongs to that IST date, and is compared against THAT
    date's 09:00 - not the previous day's."""
    v = verdict(ist(0, 30), ist(1, 30))
    assert v.scheduled_start_at == ist(9, 0)
    assert v.worked_minutes == 60
    assert v.classification == CLASSIFICATION_PRESENT


# ── the grace period, isolated ──────────────────────────────────────────────

def test_grace_is_zero_until_management_answers_o3():
    assert SHORTFALL_GRACE_MINUTES == 0


def test_grace_now_controls_only_whether_the_shortfall_is_reported():
    """Since completeness settles the day, grace no longer changes the verdict -
    it decides whether the shortfall is worth mentioning at all."""
    short = summarize_day([ist(9, 10), ist(17, 10)])  # 8h against 8h 30m
    without = classify_day(short, day=DAY, shift=CHENNAI)
    with_grace = classify_day(short, day=DAY, shift=CHENNAI, grace_minutes=30)

    assert without.classification == CLASSIFICATION_PRESENT
    assert with_grace.classification == CLASSIFICATION_PRESENT
    assert REASON_SHORT_OF_SCHEDULED in without.reasons
    assert REASON_SHORT_OF_SCHEDULED not in with_grace.reasons


def test_exactly_at_the_grace_boundary_reports_no_shortfall():
    v = classify_day(
        summarize_day([ist(9, 10), ist(17, 30)]), day=DAY, shift=CHENNAI, grace_minutes=10
    )
    assert v.worked_minutes == 500
    assert v.classification == CLASSIFICATION_PRESENT
    assert REASON_SHORT_OF_SCHEDULED not in v.reasons


# ── the vocabulary itself ───────────────────────────────────────────────────

def test_no_classification_encodes_a_cause():
    """The guard against the whole failure mode: biometric evidence cannot say
    WHY somebody was not at work, so these words must never appear."""
    forbidden = {"absent", "half_day", "permission", "leave", "holiday", "comp_off"}
    assert forbidden.isdisjoint(set(CLASSIFICATIONS))


def test_the_classification_vocabulary_is_exactly_four_values():
    assert set(CLASSIFICATIONS) == {
        CLASSIFICATION_PRESENT,
        CLASSIFICATION_INCOMPLETE,
        CLASSIFICATION_NEEDS_REVIEW,
        CLASSIFICATION_NO_RECORD,
    }


def test_a_classification_is_not_an_attendance_status():
    """Deliberately separate enums. If these ever unify it must be a decision,
    not an accident of importing the wrong name."""
    from app.modules.attendance.models import AttendanceStatus

    official = {s.value for s in AttendanceStatus}
    assert set(CLASSIFICATIONS) - official == {
        CLASSIFICATION_INCOMPLETE,
        CLASSIFICATION_NEEDS_REVIEW,
        CLASSIFICATION_NO_RECORD,
    }


# ── the endpoint ────────────────────────────────────────────────────────────

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
            raw_punch_state="0",
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


@pytest.fixture()
def chennai(db):
    """The real office configuration: 09:00 - 17:30 Asia/Kolkata, 30m break."""
    office = Office(
        name="Chennai P7",
        timezone="Asia/Kolkata",
        shift_start=DEFAULT_SHIFT_START,
        shift_end=DEFAULT_SHIFT_END,
        break_minutes=30,
    )
    db.add(office)
    db.commit()
    return office


def _summary(client, headers, *, date_from="2026-07-29", date_to="2026-07-29", **extra):
    res = client.get(
        SUMMARY, params={"from": date_from, "to": date_to, **extra}, headers=headers
    )
    assert res.status_code == 200, res.text
    return res.json()


def _employee_at(db, make_employee, office, **kw):
    emp = make_employee(**kw)
    emp.office_id = office.id
    db.add(emp)
    db.commit()
    return emp


def test_the_endpoint_reports_a_complete_day_from_office_configuration(
    client, pm, punch, mapping, make_employee, chennai, db
):
    emp = _employee_at(db, make_employee, chennai, employee_code="EMP101")
    mapping("101", emp.id)
    punch("101", ist(9, 0))
    punch("101", ist(17, 30))

    row = _summary(client, pm)["items"][0]
    assert row["worked_minutes"] == 510
    assert row["scheduled_minutes"] == 510
    assert row["scheduled_start_at"].startswith("2026-07-29T03:30")  # 09:00 IST
    assert row["scheduled_end_at"].startswith("2026-07-29T12:00")    # 17:30 IST
    assert row["shift_source"] == SHIFT_SOURCE_OFFICE
    assert row["classification"] == CLASSIFICATION_PRESENT
    assert row["review_required"] is False
    assert row["review_reasons"] == []


def test_the_endpoint_reports_a_short_day_as_complete_without_naming_a_cause(
    client, pm, punch, mapping, make_employee, chennai, db
):
    emp = _employee_at(db, make_employee, chennai, employee_code="EMP102")
    mapping("102", emp.id)
    punch("102", ist(9, 10))
    punch("102", ist(17, 10))

    row = _summary(client, pm)["items"][0]
    assert row["worked_minutes"] == 480
    # Complete evidence: settled, with the shortfall reported as context.
    assert row["classification"] == CLASSIFICATION_PRESENT
    assert row["review_required"] is False
    assert REASON_SHORT_OF_SCHEDULED in row["review_reasons"]
    assert "half_day" not in row["classification"]


def test_the_endpoint_reports_a_single_punch_as_incomplete(
    client, pm, punch, mapping, make_employee, chennai, db
):
    emp = _employee_at(db, make_employee, chennai, employee_code="EMP103")
    mapping("103", emp.id)
    punch("103", ist(9, 15))

    row = _summary(client, pm)["items"][0]
    assert row["last_out"] is None
    assert row["worked_minutes"] is None
    assert row["classification"] == CLASSIFICATION_INCOMPLETE
    assert row["review_required"] is True
    # The scheduled end is known and reported - and is NOT used as an OUT.
    assert row["scheduled_end_at"] is not None


def test_a_day_with_no_punches_produces_no_row_at_all(
    client, pm, mapping, make_employee, chennai, db
):
    """No biometric record is an ABSENCE OF EVIDENCE, so there is nothing to
    classify and no row is invented. It is emphatically not reported as absent."""
    emp = _employee_at(db, make_employee, chennai, employee_code="EMP104")
    mapping("104", emp.id)

    payload = _summary(client, pm)
    assert payload["items"] == []
    assert payload["total"] == 0


def test_an_employee_with_no_office_falls_back_and_says_so(
    client, pm, punch, mapping, make_employee
):
    emp = make_employee(employee_code="EMP105")  # office_id is nullable
    mapping("105", emp.id)
    punch("105", ist(9, 0))
    punch("105", ist(17, 30))

    row = _summary(client, pm)["items"][0]
    assert row["shift_source"] == SHIFT_SOURCE_DEFAULT
    assert row["scheduled_minutes"] == SCHEDULED_MINUTES
    assert REASON_DEFAULT_SHIFT_ASSUMED in row["review_reasons"]
    assert row["classification"] == CLASSIFICATION_PRESENT


def test_each_employee_is_compared_against_their_own_office_window(
    client, pm, punch, mapping, make_employee, chennai, db
):
    """A 09:00 - 18:00 office is 540 minutes, so the identical punch pair that
    meets Chennai's window falls short there. No global constant flattens this -
    the shortfall is reported per office even though both days are settled."""
    qatar = Office(
        name="Qatar P7",
        timezone="Asia/Kolkata",  # same zone: this test is about the WINDOW only
        shift_start=dtime(9, 0),
        shift_end=dtime(18, 0),
        break_minutes=60,
    )
    db.add(qatar)
    db.commit()

    here = _employee_at(db, make_employee, chennai, employee_code="EMP106")
    there = _employee_at(db, make_employee, qatar, employee_code="EMP107")
    mapping("106", here.id)
    mapping("107", there.id)
    for code in ("106", "107"):
        punch(code, ist(9, 0))
        punch(code, ist(17, 30))

    rows = {r["employee_code"]: r for r in _summary(client, pm)["items"]}
    assert rows["EMP106"]["scheduled_minutes"] == 510
    assert rows["EMP106"]["classification"] == CLASSIFICATION_PRESENT
    assert REASON_SHORT_OF_SCHEDULED not in rows["EMP106"]["review_reasons"]
    assert rows["EMP107"]["scheduled_minutes"] == 540
    assert rows["EMP107"]["classification"] == CLASSIFICATION_PRESENT
    # Same punches, longer contracted day - only THIS office reports a shortfall.
    assert REASON_SHORT_OF_SCHEDULED in rows["EMP107"]["review_reasons"]


def test_the_page_declares_the_grace_period_it_applied(
    client, pm, punch, mapping, make_employee, chennai, db
):
    emp = _employee_at(db, make_employee, chennai, employee_code="EMP108")
    mapping("108", emp.id)
    punch("108", ist(9, 0))

    assert _summary(client, pm)["grace_minutes"] == SHORTFALL_GRACE_MINUTES


def test_the_phase_6_fields_are_unchanged(
    client, pm, punch, mapping, make_employee, chennai, db
):
    """Phase 7 is additive. Everything Phase 6 promised still arrives."""
    emp = _employee_at(db, make_employee, chennai, employee_code="EMP109")
    mapping("109", emp.id)
    punch("109", ist(9, 5, 0))
    punch("109", ist(9, 5, 12))  # re-scan
    punch("109", ist(17, 35))

    row = _summary(client, pm)["items"][0]
    assert row["punch_count"] == 3
    assert row["kept_count"] == 2
    assert len(row["punch_times"]) == 2
    assert row["external_employee_codes"] == ["109"]
    assert row["first_in"] == row["punch_times"][0]
    assert row["last_out"] == row["punch_times"][-1]
    # And the Phase 7 verdict on the same row.
    assert row["worked_minutes"] == 510
    assert row["classification"] == CLASSIFICATION_PRESENT


def test_an_employee_sees_the_classification_of_their_own_day(
    client, login, make_user, punch, mapping, make_employee, chennai, db
):
    user = make_user("own@x.com", role=UserRole.employee)
    emp = _employee_at(
        db, make_employee, chennai, employee_code="EMP110", user_id=user.id
    )
    mapping("110", emp.id)
    punch("110", ist(9, 0))
    punch("110", ist(17, 30))

    items = _summary(client, login("own@x.com"))["items"]
    assert items[0]["classification"] == CLASSIFICATION_PRESENT


def test_a_mapping_added_later_makes_old_punches_classifiable(
    client, pm, punch, mapping, make_employee, chennai, db
):
    """Phase 5/6 behaviour, re-verified at the Phase 7 layer: the classification
    follows the mapping table, and no punch is rewritten to achieve it."""
    emp = _employee_at(db, make_employee, chennai, employee_code="EMP111")
    punch("111", ist(9, 0))
    punch("111", ist(17, 30))
    assert _summary(client, pm)["items"] == []

    mapping("111", emp.id)
    row = _summary(client, pm)["items"][0]
    assert row["classification"] == CLASSIFICATION_PRESENT
    assert db.execute(
        select(func.count())
        .select_from(BiometricPunch)
        .where(BiometricPunch.employee_id.isnot(None))
    ).scalar_one() == 0


def test_an_unmapped_code_is_never_attributed_or_classified(
    client, pm, punch, make_employee, chennai, db
):
    _employee_at(db, make_employee, chennai, employee_code="EMP112")  # no mapping
    punch("112", ist(9, 0))
    punch("112", ist(17, 30))

    assert _summary(client, pm)["items"] == []


def test_classification_writes_absolutely_nothing(
    client, pm, punch, mapping, make_employee, chennai, db
):
    """The shadow guarantee, at the Phase 7 layer: repeated reads mutate no punch,
    create no attendance record, and attribute no punch row."""
    emp = _employee_at(db, make_employee, chennai, employee_code="EMP113")
    mapping("113", emp.id)
    punch("113", ist(9, 10))
    punch("113", ist(17, 10))

    fingerprint = select(func.md5(func.string_agg(cast(BiometricPunch.id, Text), ",")))
    before = db.execute(fingerprint).scalar_one()
    mappings_before = db.execute(
        select(func.count()).select_from(BiometricEmployeeMapping)
    ).scalar_one()

    _summary(client, pm)
    _summary(client, pm)
    _summary(client, pm)

    assert db.execute(fingerprint).scalar_one() == before
    assert db.execute(
        select(func.count()).select_from(AttendanceRecord)
    ).scalar_one() == 0
    assert db.execute(
        select(func.count()).select_from(BiometricEmployeeMapping)
    ).scalar_one() == mappings_before
    assert db.execute(
        select(func.count())
        .select_from(BiometricPunch)
        .where(BiometricPunch.employee_id.isnot(None))
    ).scalar_one() == 0
