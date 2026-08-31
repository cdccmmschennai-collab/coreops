"""Phase 3F - reconciling automatic LEAVE reports when the absence ends.

An automatic leave report is LOCKED (Phase 3E), which is correct only while the
absence it was written for stands. These tests pin what happens when it stops
standing, by both routes:

    formal cancellation   approved -> cancellation_requested -> cancelled
    a PM re-deciding      attendance_records: leave -> present (or anything else)

and, just as importantly, what does NOT happen: a merely REQUESTED withdrawal, a
REJECTED one, an employee's own leave report, an automatic week-off report,
another employee and another date are all left exactly alone.

    docker exec wms-backend-1 pytest tests/test_auto_leave_reconciliation.py

CALENDAR ANCHORS
================
Shared with `test_auto_leave_reports.py` and pinned the same way: the office week
is Mon-Fri plus the 1st/3rd/5th Saturday, so in August 2026 the 22nd is a
genuinely non-working (4th) Saturday and 17-21 Aug are five ordinary weekdays.
"""
from datetime import date

import pytest

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.attendance.schemas import (
    AttendanceBulkRecord,
    AttendanceCreate,
    AttendanceUpdate,
)
from app.modules.leave.models import LeaveStatus
from app.modules.users.models import UserRole
from app.modules.work_reports.auto_reports import (
    AUTO_LEAVE_DAY_STATUS,
    AUTO_WEEKEND_DAY_STATUS,
    auto_report_author_editable,
    generate_auto_leave_reports,
    generate_auto_reports,
    is_untouched_auto_report,
    leave_is_active_on,
    reconcile_auto_leave_report,
    reconcile_auto_leave_reports,
)
from app.modules.work_reports.models import (
    DailyWorkReport,
    DayPart,
    DayStatus,
    ReportMode,
    ReportOrigin,
    WorkReportPeriod,
    WorkReportStatus,
)

_MON = date(2026, 8, 17)
_TUE = date(2026, 8, 18)
_WED = date(2026, 8, 19)
_THU = date(2026, 8, 20)
_FRI = date(2026, 8, 21)
_WEEK = [_MON, _TUE, _WED, _THU, _FRI]
# The 4th Saturday - non-working, so the WEEK-OFF sweep owns it.
_SAT_OFF = date(2026, 8, 22)


def test_calendar_anchors_are_the_days_these_tests_assume():
    from app.modules.calendar.working_days import saturday_occurrence

    assert [d.weekday() for d in _WEEK] == [0, 1, 2, 3, 4]
    assert _SAT_OFF.weekday() == 5 and saturday_occurrence(_SAT_OFF) == 4


# --- fixtures / helpers -----------------------------------------------------


@pytest.fixture()
def pm(make_user, make_employee):
    """A project manager - the only actor who may decide a cancellation."""
    user = make_user("pm-3f@example.com", role=UserRole.project_manager)
    make_employee(employee_code="PM-3F", user_id=user.id)
    return user


@pytest.fixture()
def employee_user(make_user):
    return make_user("emp-3f@example.com")


@pytest.fixture()
def employee(make_employee, employee_user):
    return make_employee(
        employee_code="EMP-3F",
        first_name="Santosh",
        last_name="Kumar",
        user_id=employee_user.id,
    )


@pytest.fixture()
def other_employee(make_employee):
    return make_employee(employee_code="EMP-3F-OTHER", first_name="Other")


@pytest.fixture()
def approved_week(make_leave_request, employee):
    """Approved leave over the whole of Mon 17 - Fri 21 Aug 2026."""
    return make_leave_request(
        employee_id=employee.id,
        start_date=_MON,
        end_date=_FRI,
        status=LeaveStatus.approved,
    )


def _generate(db, dates=None):
    return generate_auto_leave_reports(db, dates=list(dates or _WEEK))


def _report(db, employee_id, day):
    db.expire_all()
    return (
        db.query(DailyWorkReport)
        .filter(
            DailyWorkReport.employee_id == employee_id,
            DailyWorkReport.report_date == day,
        )
        .one_or_none()
    )


def _dates_of(db, employee_id):
    db.expire_all()
    return sorted(
        r.report_date
        for r in db.query(DailyWorkReport)
        .filter(DailyWorkReport.employee_id == employee_id)
        .all()
    )


def _set_status(db, req, status):
    """Move a leave request without going through the service - for the states a
    test needs to START in rather than to exercise."""
    req.status = status
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def _attendance(db, employee_id, day, status=AttendanceStatus.leave):
    """The row an approval writes for a leave day: status leave, no times."""
    record = AttendanceRecord(
        employee_id=employee_id,
        attendance_date=day,
        status=status,
        check_in_at=None,
        check_out_at=None,
        total_minutes=0,
        overtime_minutes=0,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _week_pairs(employee_id, days=None):
    return [(employee_id, d) for d in (days or _WEEK)]


# ===========================================================================
# A. an absence that still stands
# ===========================================================================


def test_active_approved_leave_keeps_its_report_and_its_lock(
    db, employee, approved_week
):
    _generate(db)
    report = _report(db, employee.id, _WED)
    assert report is not None and report.day_status == AUTO_LEAVE_DAY_STATUS
    assert auto_report_author_editable(report) is False

    result = reconcile_auto_leave_reports(db, _week_pairs(employee.id))

    assert result.examined == 5
    assert result.still_on_leave == 5
    assert result.deleted == 0 and result.reclassified == 0
    survivor = _report(db, employee.id, _WED)
    assert survivor.id == report.id
    assert survivor.day_status == AUTO_LEAVE_DAY_STATUS
    assert survivor.status == WorkReportStatus.submitted
    assert auto_report_author_editable(survivor) is False


def test_leave_is_active_on_says_yes_for_approved_leave(db, employee, approved_week):
    assert leave_is_active_on(db, employee.id, _WED) is True
    # Outside the range.
    assert leave_is_active_on(db, employee.id, _SAT_OFF) is False


# ===========================================================================
# B. cancellation merely REQUESTED - the absence stands
# ===========================================================================


def test_cancellation_requested_keeps_the_report_locked(
    db, employee, approved_week
):
    _generate(db)
    _set_status(db, approved_week, LeaveStatus.cancellation_requested)

    result = reconcile_auto_leave_reports(db, _week_pairs(employee.id))

    assert result.still_on_leave == 5
    assert result.deleted == 0 and result.reclassified == 0
    assert _dates_of(db, employee.id) == _WEEK
    assert auto_report_author_editable(_report(db, employee.id, _WED)) is False


def test_leave_is_active_on_counts_a_requested_withdrawal_as_active(
    db, employee, approved_week
):
    """The deliberate difference between `ACTIVE_LEAVE_STATUSES` (keeps a report)
    and `AUTO_LEAVE_STATUSES` (writes one)."""
    _set_status(db, approved_week, LeaveStatus.cancellation_requested)

    assert leave_is_active_on(db, employee.id, _WED) is True


def test_requesting_cancellation_through_the_api_does_not_reconcile(
    db, client, login, make_user, make_employee, make_leave_request
):
    """The employee-facing transition itself: approved -> cancellation_requested
    must leave every automatic report exactly where it is."""
    from datetime import timedelta

    user = make_user("withdraw@example.com")
    pm_user = make_user("withdraw-pm@example.com", role=UserRole.project_manager)
    make_employee(employee_code="EMP-WDR-PM", user_id=pm_user.id)
    emp = make_employee(
        employee_code="EMP-WDR", user_id=user.id, reporting_pm_id=pm_user.id
    )
    # `request-cancellation` refuses leave that has already ended, so this one is
    # in the future - the exact dates do not matter, only that they are working
    # days the generator will file.
    start = date.today() + timedelta(days=7)
    req = make_leave_request(
        employee_id=emp.id,
        start_date=start,
        end_date=start,
        status=LeaveStatus.approved,
    )
    generate_auto_leave_reports(db, dates=[start])
    before = _report(db, emp.id, start)
    if before is None:
        pytest.skip("the chosen future date is not a working day on this calendar")

    res = client.post(
        f"/api/v1/leave-requests/{req.id}/request-cancellation",
        headers=login("withdraw@example.com"),
    )

    assert res.status_code == 200, res.text
    assert res.json()["status"] == "cancellation_requested"
    after = _report(db, emp.id, start)
    assert after is not None and after.id == before.id
    assert after.day_status == AUTO_LEAVE_DAY_STATUS
    assert auto_report_author_editable(after) is False


# ===========================================================================
# C. cancellation REJECTED - the leave stands again
# ===========================================================================


def test_rejecting_the_cancellation_leaves_the_report_locked(
    db, pm, employee, approved_week
):
    from app.modules.leave import service as leave_service

    _generate(db)
    _set_status(db, approved_week, LeaveStatus.cancellation_requested)

    leave_service.reject_leave_cancellation(db, pm, approved_week.id)

    db.refresh(approved_week)
    assert approved_week.status == LeaveStatus.approved
    assert _dates_of(db, employee.id) == _WEEK
    report = _report(db, employee.id, _WED)
    assert report.day_status == AUTO_LEAVE_DAY_STATUS
    assert report.status == WorkReportStatus.submitted
    assert auto_report_author_editable(report) is False
    # And an explicit reconciliation afterwards still finds nothing to do.
    assert reconcile_auto_leave_reports(db, _week_pairs(employee.id)).deleted == 0


# ===========================================================================
# D. cancellation APPROVED - the absence is over
# ===========================================================================


def test_approving_the_cancellation_removes_the_untouched_auto_reports(
    db, pm, employee, approved_week
):
    from app.modules.leave import service as leave_service

    _generate(db)
    assert _dates_of(db, employee.id) == _WEEK
    _set_status(db, approved_week, LeaveStatus.cancellation_requested)

    leave_service.approve_leave_cancellation(db, pm, approved_week.id)

    db.refresh(approved_week)
    assert approved_week.status == LeaveStatus.cancelled
    # Every slot is free again, so the employee can file the ordinary reports the
    # days now need.
    assert _dates_of(db, employee.id) == []


def test_the_freed_slot_accepts_a_normal_report(db, pm, employee, approved_week):
    """"Normal reporting can resume" stated as the thing that was impossible
    before: the unique constraint on (employee, date) is what the locked shell was
    occupying."""
    from app.modules.leave import service as leave_service

    _generate(db)
    _set_status(db, approved_week, LeaveStatus.cancellation_requested)
    leave_service.approve_leave_cancellation(db, pm, approved_week.id)

    db.add(
        DailyWorkReport(
            employee_id=employee.id,
            report_date=_WED,
            status=WorkReportStatus.draft,
            origin=ReportOrigin.employee,
            report_mode=ReportMode.full_day.value,
            day_status=DayStatus.work_at_office,
            total_minutes=480,
        )
    )
    db.commit()

    mine = _report(db, employee.id, _WED)
    assert mine.origin == ReportOrigin.employee
    assert mine.status == WorkReportStatus.draft


def test_a_cancelled_leave_is_no_longer_active(db, employee, approved_week):
    _set_status(db, approved_week, LeaveStatus.cancelled)

    assert leave_is_active_on(db, employee.id, _WED) is False


def test_cancelling_a_pending_request_is_a_harmless_no_op(
    db, client, login, make_user, make_employee, make_leave_request
):
    """The direct pending -> cancelled path is hooked for completeness. A pending
    leave never generated anything, so there is nothing to take back - and the
    employee's own report for the same date must survive it."""
    from datetime import timedelta

    user = make_user("pendcancel@example.com")
    emp = make_employee(employee_code="EMP-PEND", user_id=user.id)
    start = date.today() + timedelta(days=9)
    req = make_leave_request(
        employee_id=emp.id, start_date=start, end_date=start
    )
    db.add(
        DailyWorkReport(
            employee_id=emp.id,
            report_date=start,
            status=WorkReportStatus.submitted,
            origin=ReportOrigin.employee,
            report_mode=ReportMode.full_day.value,
            day_status=DayStatus.leave,
            total_minutes=0,
        )
    )
    db.commit()

    res = client.post(
        f"/api/v1/leave-requests/{req.id}/cancel",
        headers=login("pendcancel@example.com"),
    )

    assert res.status_code == 200, res.text
    survivor = _report(db, emp.id, start)
    assert survivor is not None
    assert survivor.origin == ReportOrigin.employee


# ===========================================================================
# E / F. a PM re-deciding the day
# ===========================================================================


@pytest.mark.parametrize(
    "new_status",
    [
        AttendanceStatus.present,
        AttendanceStatus.absent,
        AttendanceStatus.half_day,
        AttendanceStatus.comp_off,
    ],
)
def test_pm_moving_the_day_off_leave_reconciles_that_day(
    db, pm, employee, approved_week, new_status
):
    from app.modules.attendance import service as attendance_service

    _generate(db)
    record = _attendance(db, employee.id, _WED)

    attendance_service.update_attendance(
        db, pm, record.id, AttendanceUpdate(status=new_status)
    )

    # Exactly that day, and nothing either side of it.
    assert _report(db, employee.id, _WED) is None
    assert _dates_of(db, employee.id) == [_MON, _TUE, _THU, _FRI]
    assert leave_is_active_on(db, employee.id, _WED) is False


def test_a_pm_change_back_to_leave_reconciles_nothing(
    db, pm, employee, approved_week
):
    from app.modules.attendance import service as attendance_service

    _generate(db)
    record = _attendance(db, employee.id, _WED)

    attendance_service.update_attendance(
        db, pm, record.id, AttendanceUpdate(status=AttendanceStatus.leave)
    )

    assert _dates_of(db, employee.id) == _WEEK
    assert auto_report_author_editable(_report(db, employee.id, _WED)) is False


def test_the_bulk_sheet_reconciles_only_the_rows_it_moved_off_leave(
    db, pm, employee, other_employee, approved_week, make_leave_request
):
    from app.modules.attendance import service as attendance_service

    make_leave_request(
        employee_id=other_employee.id,
        start_date=_WED,
        end_date=_WED,
        status=LeaveStatus.approved,
    )
    _generate(db)
    _attendance(db, employee.id, _WED)
    _attendance(db, other_employee.id, _WED)

    attendance_service.bulk_save_attendance(
        db,
        pm,
        _WED,
        [
            AttendanceBulkRecord(
                employee_id=employee.id, status=AttendanceStatus.present
            ),
            AttendanceBulkRecord(
                employee_id=other_employee.id, status=AttendanceStatus.leave
            ),
        ],
    )

    assert _report(db, employee.id, _WED) is None
    still_on_leave = _report(db, other_employee.id, _WED)
    assert still_on_leave is not None
    assert still_on_leave.day_status == AUTO_LEAVE_DAY_STATUS


def test_creating_a_non_leave_attendance_row_reconciles_too(
    db, pm, employee, approved_week
):
    """`create_attendance` is the third write path in the module and follows the
    same rule, so the three cannot drift."""
    from app.modules.attendance import service as attendance_service

    _generate(db)

    attendance_service.create_attendance(
        db,
        pm,
        AttendanceCreate(
            employee_id=employee.id,
            attendance_date=_WED,
            status=AttendanceStatus.present,
        ),
    )

    assert _report(db, employee.id, _WED) is None


def test_the_01_00_sweep_does_not_undo_a_pm_attendance_change(
    db, pm, employee, approved_week
):
    """Without the generation guard the reconciliation would last until 01:00 and
    no longer: the leave request is still `approved`, so the sweep would refile
    the very report the PM's change removed."""
    from app.modules.attendance import service as attendance_service

    _generate(db)
    record = _attendance(db, employee.id, _WED)
    attendance_service.update_attendance(
        db, pm, record.id, AttendanceUpdate(status=AttendanceStatus.present)
    )
    assert _report(db, employee.id, _WED) is None

    result = _generate(db)

    assert _report(db, employee.id, _WED) is None
    assert result.created == 0
    # The other four days were never re-decided and keep their reports.
    assert _dates_of(db, employee.id) == [_MON, _TUE, _THU, _FRI]


def test_a_day_with_no_attendance_row_is_still_on_leave(
    db, pm, employee, approved_week
):
    """`reverse_leave_approved` DELETES the rows it wrote, so "no row" must not
    read as "the employee worked"."""
    _generate(db)

    result = reconcile_auto_leave_reports(db, [(employee.id, _WED)])

    assert result.still_on_leave == 1
    assert _report(db, employee.id, _WED) is not None


# ===========================================================================
# G / H / I / J. everything reconciliation must not touch
# ===========================================================================


def test_an_employee_authored_leave_report_is_never_reconciled(
    db, employee, approved_week
):
    db.add(
        DailyWorkReport(
            employee_id=employee.id,
            report_date=_WED,
            status=WorkReportStatus.submitted,
            origin=ReportOrigin.employee,
            report_mode=ReportMode.full_day.value,
            day_status=DayStatus.leave,
            total_minutes=0,
            remarks="I filed this myself.",
        )
    )
    db.commit()
    _set_status(db, approved_week, LeaveStatus.cancelled)

    result = reconcile_auto_leave_reports(db, [(employee.id, _WED)])

    assert result.examined == 0
    assert result.deleted == 0 and result.reclassified == 0
    mine = _report(db, employee.id, _WED)
    assert mine is not None
    assert mine.origin == ReportOrigin.employee
    assert mine.day_status == DayStatus.leave
    assert mine.status == WorkReportStatus.submitted
    assert mine.remarks == "I filed this myself."


def test_an_auto_week_off_report_is_never_reconciled_by_leave(db, employee):
    """Phase 3D's rows carry a different day_status and are outside every query
    here - the mirror of `test_calendar_reconciliation_never_touches_an_auto_leave
    _report` in the Phase 3E suite."""
    generate_auto_reports(db, dates=[_SAT_OFF])
    weekend = _report(db, employee.id, _SAT_OFF)
    assert weekend is not None and weekend.day_status == AUTO_WEEKEND_DAY_STATUS

    result = reconcile_auto_leave_reports(db, [(employee.id, _SAT_OFF)])

    assert result.examined == 0
    survivor = _report(db, employee.id, _SAT_OFF)
    assert survivor.id == weekend.id
    assert survivor.day_status == AUTO_WEEKEND_DAY_STATUS
    assert survivor.status == WorkReportStatus.submitted


def test_another_employee_on_the_same_date_is_untouched(
    db, employee, other_employee, approved_week, make_leave_request
):
    make_leave_request(
        employee_id=other_employee.id,
        start_date=_WED,
        end_date=_WED,
        status=LeaveStatus.approved,
    )
    _generate(db, [_WED])
    _set_status(db, approved_week, LeaveStatus.cancelled)

    reconcile_auto_leave_reports(db, [(employee.id, _WED)])

    assert _report(db, employee.id, _WED) is None
    theirs = _report(db, other_employee.id, _WED)
    assert theirs is not None and theirs.day_status == AUTO_LEAVE_DAY_STATUS


def test_another_date_for_the_same_employee_is_untouched(
    db, employee, approved_week
):
    _generate(db)
    _set_status(db, approved_week, LeaveStatus.cancelled)

    reconcile_auto_leave_report(db, employee.id, _WED)

    assert _dates_of(db, employee.id) == [_MON, _TUE, _THU, _FRI]


def test_the_pair_scope_is_pairs_not_a_rectangle(
    db, employee, other_employee, approved_week, make_leave_request
):
    """Two employees and two dates named as two PAIRS must not reconcile the
    other two corners of the 2x2."""
    make_leave_request(
        employee_id=other_employee.id,
        start_date=_MON,
        end_date=_FRI,
        status=LeaveStatus.approved,
    )
    _generate(db, [_WED, _THU])
    for req in db.query(type(approved_week)).all():
        _set_status(db, req, LeaveStatus.cancelled)

    reconcile_auto_leave_reports(
        db, [(employee.id, _WED), (other_employee.id, _THU)]
    )

    assert _dates_of(db, employee.id) == [_THU]
    assert _dates_of(db, other_employee.id) == [_WED]


# ===========================================================================
# K. an automatic leave report somebody has typed on
# ===========================================================================


def test_a_touched_auto_leave_report_is_preserved_and_unlocked(
    db, employee, approved_week
):
    _generate(db, [_WED])
    report = _report(db, employee.id, _WED)
    report_id = report.id
    # Something only a person can have put there.
    report.remarks = "Came in for two hours to close the pending punch list."
    db.add(report)
    db.commit()
    assert (
        is_untouched_auto_report(db, report, day_status=AUTO_LEAVE_DAY_STATUS)
        is False
    )
    _set_status(db, approved_week, LeaveStatus.cancelled)

    result = reconcile_auto_leave_reports(db, [(employee.id, _WED)])

    assert result.reclassified == 1 and result.deleted == 0
    kept = _report(db, employee.id, _WED)
    assert kept.id == report_id
    # The employee's data survives, in full.
    assert kept.remarks == "Came in for two hours to close the pending punch list."
    # The withdrawn label, and the reopen that goes with it.
    assert kept.day_status is None
    assert kept.status == WorkReportStatus.draft
    assert kept.submitted_at is None
    # `origin` is permanent provenance, never rewritten.
    assert kept.origin == ReportOrigin.auto
    # And it is no longer locked - `day_status` is out of AUTO_LOCKED_DAY_STATUSES.
    assert auto_report_author_editable(kept) is True


def test_reclassifying_clears_the_generated_period_status(
    db, employee, approved_week
):
    _generate(db, [_WED])
    report = _report(db, employee.id, _WED)
    report.remarks = "Half a day of handover."
    db.add(report)
    db.commit()
    _set_status(db, approved_week, LeaveStatus.cancelled)

    reconcile_auto_leave_reports(db, [(employee.id, _WED)])

    db.expire_all()
    periods = (
        db.query(WorkReportPeriod)
        .filter(WorkReportPeriod.report_id == report.id)
        .all()
    )
    assert len(periods) == 1
    assert periods[0].day_part == DayPart.full_day.value
    assert periods[0].period_status is None


def test_zero_minutes_alone_never_makes_a_report_untouched(
    db, employee, approved_week
):
    """Every automatic leave report has `total_minutes == 0`, including one
    somebody has typed on - so the signature has to cover the whole row."""
    _generate(db, [_WED])
    report = _report(db, employee.id, _WED)
    report.query_text = "Do I need to file anything for this day?"
    db.add(report)
    db.commit()

    assert report.total_minutes == 0
    assert (
        is_untouched_auto_report(db, report, day_status=AUTO_LEAVE_DAY_STATUS)
        is False
    )


def test_the_untouched_predicate_will_not_cross_between_the_two_shapes(
    db, employee, approved_week
):
    """A generated LEAVE row is not the generated WEEK-OFF shape and vice versa,
    which is what keeps the two reconciliations off each other's rows."""
    _generate(db, [_WED])
    leave_report = _report(db, employee.id, _WED)
    generate_auto_reports(db, dates=[_SAT_OFF])
    weekend_report = _report(db, employee.id, _SAT_OFF)

    assert is_untouched_auto_report(
        db, leave_report, day_status=AUTO_LEAVE_DAY_STATUS
    )
    assert not is_untouched_auto_report(db, leave_report)
    assert is_untouched_auto_report(db, weekend_report)
    assert not is_untouched_auto_report(
        db, weekend_report, day_status=AUTO_LEAVE_DAY_STATUS
    )


# ===========================================================================
# L. idempotency
# ===========================================================================


def test_reconciling_twice_produces_the_same_state(db, employee, approved_week):
    _generate(db)
    _set_status(db, approved_week, LeaveStatus.cancelled)

    first = reconcile_auto_leave_reports(db, _week_pairs(employee.id))
    second = reconcile_auto_leave_reports(db, _week_pairs(employee.id))

    assert first.deleted == 5
    assert second.examined == 0
    assert second.deleted == 0 and second.reclassified == 0
    assert _dates_of(db, employee.id) == []


def test_reconciling_a_reclassified_report_twice_changes_nothing(
    db, employee, approved_week
):
    _generate(db, [_WED])
    report = _report(db, employee.id, _WED)
    report.remarks = "Worked the afternoon."
    db.add(report)
    db.commit()
    _set_status(db, approved_week, LeaveStatus.cancelled)

    reconcile_auto_leave_reports(db, [(employee.id, _WED)])
    second = reconcile_auto_leave_reports(db, [(employee.id, _WED)])

    assert second.examined == 0
    kept = _report(db, employee.id, _WED)
    assert kept.day_status is None
    assert kept.status == WorkReportStatus.draft
    assert kept.remarks == "Worked the afternoon."


def test_an_empty_target_set_is_a_no_op(db, employee, approved_week):
    _generate(db)

    result = reconcile_auto_leave_reports(db, [])

    assert result.dates == []
    assert result.examined == 0
    assert _dates_of(db, employee.id) == _WEEK
