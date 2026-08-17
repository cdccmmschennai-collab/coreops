"""Tests for the Daily Report Reminder.

The reminder checks exactly ONE date: the immediately previous working day.
Covered here: the previous-working-day resolution (weekends + company calendar),
the "only that one date" collection rule, the PM-exclusion rule, and the
template / CSV rendering.
"""
import csv
import io
import uuid
from datetime import date

from app.notifications.email_service import EmailSendError
from app.reminders.daily_report.dispatcher import run_daily_report_reminders
from app.reminders.daily_report.service import (
    DailyReportReminderService,
    MissingEmployee,
    PMReminder,
)
from app.reminders.daily_report.template import render_daily_report_reminder

# Calendar anchors (2026): 10 Aug is a Monday, so 12 Aug is a Wednesday and
# 13 Aug a Thursday — the dates used in the approved specification.
_MON = date(2026, 8, 10)
_TUE = date(2026, 8, 11)
_WED = date(2026, 8, 12)
_THU = date(2026, 8, 13)
_PREV_FRI = date(2026, 8, 7)
_PREV_SAT = date(2026, 8, 8)
_PREV_SUN = date(2026, 8, 9)


# --- previous working day: pure calendar arithmetic -------------------------


def test_calendar_anchors_are_the_weekdays_the_spec_assumes():
    """Guards every date constant below against an off-by-one year change."""
    assert _MON.weekday() == 0
    assert _WED.weekday() == 2
    assert _THU.weekday() == 3
    assert _PREV_FRI.weekday() == 4
    assert _PREV_SAT.weekday() == 5
    assert _PREV_SUN.weekday() == 6


def test_is_working_day_baseline_is_mon_to_fri():
    from app.modules.calendar.working_days import is_working_day

    empty: set = set()
    assert is_working_day(_WED, non_working=empty, working_overrides=empty)
    assert is_working_day(_PREV_FRI, non_working=empty, working_overrides=empty)
    assert not is_working_day(_PREV_SAT, non_working=empty, working_overrides=empty)
    assert not is_working_day(_PREV_SUN, non_working=empty, working_overrides=empty)


def test_is_working_day_honours_holidays_and_working_day_overrides():
    from app.modules.calendar.working_days import is_working_day

    # A declared holiday closes an otherwise normal weekday.
    assert not is_working_day(_WED, non_working={_WED}, working_overrides=set())
    # A declared working day opens a Saturday...
    assert is_working_day(_PREV_SAT, non_working=set(), working_overrides={_PREV_SAT})
    # ...and wins even if the same date also carries a holiday entry.
    assert is_working_day(_WED, non_working={_WED}, working_overrides={_WED})


# --- previous working day: against the real calendar table ------------------


def _make_calendar_event(db, *, event_date, event_type, title="Test"):
    from app.modules.calendar.models import CalendarEvent, CalendarEventType

    ev = CalendarEvent(
        event_date=event_date,
        title=title,
        event_type=CalendarEventType(event_type),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def _target(db, today):
    return DailyReportReminderService().target_date(db, today)


def test_target_date_on_a_normal_weekday_is_yesterday(db):
    """Thursday 13 Aug -> Wednesday 12 Aug, exactly as specified."""
    assert _target(db, _THU) == _WED


def test_target_date_on_monday_is_the_previous_friday(db):
    assert _target(db, _MON) == _PREV_FRI


def test_target_date_from_a_weekend_skips_back_to_friday(db):
    """The weekend itself is never a target."""
    assert _target(db, _PREV_SUN) == _PREV_FRI   # run on Sunday
    assert _target(db, _PREV_SAT) == _PREV_FRI   # run on Saturday


def test_target_date_skips_a_configured_holiday(db):
    """A company-calendar holiday on the previous day is skipped."""
    _make_calendar_event(db, event_date=_WED, event_type="holiday", title="Festival")
    assert _target(db, _THU) == _TUE


def test_target_date_skips_consecutive_non_working_days(db):
    """Holiday + cdc_holiday back to back, then the weekend."""
    _make_calendar_event(db, event_date=_WED, event_type="holiday")
    _make_calendar_event(db, event_date=_TUE, event_type="cdc_holiday")
    _make_calendar_event(db, event_date=_MON, event_type="natural_hazard")
    assert _target(db, _THU) == _PREV_FRI


def test_target_date_uses_a_declared_working_saturday(db):
    """A `working_day` entry opens a normally-off day, so Monday targets it."""
    _make_calendar_event(db, event_date=_PREV_SAT, event_type="working_day")
    assert _target(db, _MON) == _PREV_SAT


def test_informational_events_do_not_close_the_office(db):
    """`event` is informational; it must not shift the target date."""
    _make_calendar_event(db, event_date=_WED, event_type="event", title="Town hall")
    assert _target(db, _THU) == _WED


def test_target_date_is_none_when_no_working_day_is_within_the_bound(db):
    """A misconfigured calendar bails out instead of looping forever."""
    from datetime import timedelta

    for offset in range(1, 6):
        _make_calendar_event(
            db, event_date=_THU - timedelta(days=offset), event_type="holiday"
        )
    svc = DailyReportReminderService(max_lookback_days=5)
    assert svc.target_date(db, _THU) is None
    assert svc.collect(db, today=_THU) == []


# --- template / CSV rendering ----------------------------------------------


def _reminder(report_date: date = _WED) -> PMReminder:
    return PMReminder(
        pm_id=uuid.uuid4(),
        pm_name="Alex",
        pm_email="alex@example.com",
        report_date=report_date,
        employees_checked=3,
        employees=[
            MissingEmployee(uuid.uuid4(), "David", "EMP001"),
            MissingEmployee(uuid.uuid4(), "John", "EMP002"),
        ],
    )


def test_subject_uses_the_target_date_not_today():
    rendered = render_daily_report_reminder(_reminder())
    assert rendered.subject == "CoreOps • Outstanding Daily Reports • 12 Aug 2026"


def test_template_text_layout_matches_the_approved_body():
    text = render_daily_report_reminder(_reminder()).text_body
    assert text.startswith("CoreOps\nOutstanding Daily Reports")
    assert "Hello Alex," in text
    assert (
        "The following employees have not submitted their daily work report "
        "for 12 Aug 2026." in text
    )
    assert "Employees with Missing Reports: 2" in text
    for header in ("Employee ID & Name", "Missing Report Date"):
        assert header in text
    assert "EMP001 - David" in text
    assert "EMP002 - John" in text
    assert text.index("David") < text.index("John")  # sorted by name
    assert (
        "Please follow up with the respective employees and ask them to submit "
        "their pending report." in text
    )
    assert text.rstrip().endswith("Automated notification - please do not reply.")


def test_only_one_date_ever_appears_per_employee():
    """One date is checked, so no row can carry a second missing-date value."""
    rendered = render_daily_report_reminder(_reminder())
    for body in (rendered.text_body, rendered.html_body):
        assert body.count("12 Aug 2026") == 3  # intro line + one cell per employee
        assert "11 Aug 2026" not in body
        assert "•" not in body                  # the old multi-date separator
    rows = _csv_rows(rendered.csv_bytes)
    assert [r["Missing Report Date"] for r in rows] == ["12 Aug 2026", "12 Aug 2026"]


def test_plain_text_fallback_has_no_html_css_or_urls():
    text = render_daily_report_reminder(_reminder()).text_body
    for token in ("<", ">", "http", "style=", "padding:", "Content-Type"):
        assert token not in text


def test_template_html_columns_summary_and_greeting():
    html = render_daily_report_reminder(_reminder()).html_body
    assert "Hello Alex" in html
    assert "Outstanding Daily Reports" in html
    assert "Employee ID &amp; Name" in html
    assert "Missing Report Date" in html
    assert ">EMP001 - David</td>" in html
    assert ">EMP002 - John</td>" in html
    assert "Employees with Missing Reports: <strong>2</strong>" in html
    assert "Automated notification - please do not reply." in html


def test_template_html_is_outlook_safe_constrained_table_layout():
    html = render_daily_report_reminder(_reminder()).html_body
    # Table-based, centered, ~700px container, white background.
    assert "max-width:700px" in html
    assert '<table role="presentation"' in html
    assert 'align="center"' in html
    assert "background:#ffffff" in html
    assert "Arial" in html
    # None of the constructs Outlook cannot render, and no marketing chrome.
    for banned in (
        "display:flex",
        "flex-direction",
        "display:grid",
        "grid-template",
        "<style",
        "<link",
        "<script",
        "<svg",
        "border-radius",
        "#0f172a",          # no dark hero/banner block
    ):
        assert banned not in html


def test_total_missing_counts_the_employees_on_the_target_day():
    assert _reminder().total_missing == 2


# --- CSV attachment ---------------------------------------------------------


def _csv_rows(csv_bytes: bytes) -> list[dict]:
    """Decode the attachment the way Excel does and parse it as CSV."""
    text = csv_bytes.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def test_csv_filename_uses_the_target_date():
    rendered = render_daily_report_reminder(_reminder())
    assert rendered.csv_filename == "coreops_outstanding_reports_2026-08-12.csv"


def test_csv_is_valid_comma_separated_content_with_bom_and_crlf():
    raw = render_daily_report_reminder(_reminder()).csv_bytes
    # Excel needs the BOM to decode UTF-8 (non-ASCII employee names) instead of
    # falling back to the local ANSI code page.
    assert raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in raw
    text = raw.decode("utf-8-sig")
    assert text.splitlines()[0] == "Employee ID,Employee Name,Missing Report Date"
    rows = _csv_rows(raw)
    assert len(rows) == 2
    assert [r["Employee ID"] for r in rows] == ["EMP001", "EMP002"]
    assert rows[0]["Employee Name"] == "David"


def test_csv_contains_only_the_recipient_pms_employees():
    mine = PMReminder(
        pm_id=uuid.uuid4(),
        pm_name="Alex",
        pm_email="alex@example.com",
        report_date=_WED,
        employees_checked=1,
        employees=[MissingEmployee(uuid.uuid4(), "David", "EMP001")],
    )
    rows = _csv_rows(render_daily_report_reminder(mine).csv_bytes)
    assert [r["Employee Name"] for r in rows] == ["David"]
    # An employee from another PM's group ("John"/EMP002) never leaks in.
    assert all(r["Employee ID"] != "EMP002" for r in rows)


# --- Failure isolation: one bad recipient must not stop the others ----------


def _pm(email: str) -> PMReminder:
    return PMReminder(
        pm_id=uuid.uuid4(),
        pm_name=email.split("@")[0],
        pm_email=email,
        report_date=_WED,
        employees_checked=1,
        employees=[MissingEmployee(uuid.uuid4(), "John", "EMP002")],
    )


class _StubService:
    """Stands in for DailyReportReminderService.collect (no DB)."""

    def __init__(self, reminders):
        self._reminders = reminders

    def collect(self, db, *, today=None):
        return self._reminders


class _StubEmailService:
    """Raises EmailSendError for one 'invalid' recipient, succeeds otherwise."""

    def __init__(self, bad_recipient):
        self.bad_recipient = bad_recipient
        self.sent_to = []
        self.sends = []

    def send(self, *, to, subject, html_body, text_body=None, attachments=None):
        if to == self.bad_recipient:
            raise EmailSendError(f"SMTP recipient refused: {to}")
        self.sent_to.append(to)
        self.sends.append(
            {"to": to, "subject": subject, "attachments": attachments or []}
        )
        return True


def test_dispatcher_routes_each_pm_their_own_csv():
    """Recipient routing is unchanged and the CSV is per-PM."""
    reminders = [_pm("alex@example.com"), _pm("dana@example.com")]
    email = _StubEmailService(bad_recipient=None)

    run_daily_report_reminders(
        db=object(), email_service=email, service=_StubService(reminders)
    )

    assert email.sent_to == ["alex@example.com", "dana@example.com"]
    for send in email.sends:
        assert len(send["attachments"]) == 1
        attachment = send["attachments"][0]
        assert attachment.filename.startswith("coreops_outstanding_reports_")
        assert attachment.filename.endswith(".csv")
        assert attachment.maintype == "text" and attachment.subtype == "csv"
        rows = _csv_rows(attachment.content)
        assert [r["Employee Name"] for r in rows] == ["John"]


def test_one_invalid_recipient_does_not_block_the_others():
    reminders = [
        _pm("alex@example.com"),
        _pm("broken@@invalid"),   # will be refused by SMTP
        _pm("dana@example.com"),
    ]
    email = _StubEmailService(bad_recipient="broken@@invalid")

    # db is unused by the stub service; pass a sentinel so no session is opened.
    result = run_daily_report_reminders(
        db=object(), email_service=email, service=_StubService(reminders)
    )

    # Successful recipients still received their emails, order preserved.
    assert email.sent_to == ["alex@example.com", "dana@example.com"]
    # The run processed every PM and completed (returned a result object).
    assert result.pms_with_missing == 3
    assert result.emails_sent == 2
    assert result.emails_failed == 1
    assert result.emails_skipped == 0

    # The failed recipient is recorded distinctly with its error captured.
    failed = [o for o in result.outcomes if o.pm_email == "broken@@invalid"]
    assert len(failed) == 1
    assert failed[0].email_sent is False
    assert failed[0].error is not None
    # The good ones are marked sent with no error.
    good = [o for o in result.outcomes if o.pm_email != "broken@@invalid"]
    assert all(o.email_sent and o.error is None for o in good)


def test_no_missing_employees_sends_no_email():
    """The existing no-email behaviour is unchanged: nothing to chase, nothing
    collected, nothing sent."""
    email = _StubEmailService(bad_recipient=None)

    result = run_daily_report_reminders(
        db=object(), email_service=email, service=_StubService([])
    )

    assert email.sent_to == []
    assert result.pms_with_missing == 0
    assert result.emails_sent == 0
    assert result.emails_skipped == 0
    assert result.emails_failed == 0
    assert result.total_missing == 0


# --- collection against the real DB ----------------------------------------


def _make_pm_user(db, email: str):
    from app.core.security import hash_password
    from app.modules.users.models import User, UserRole

    user = User(
        email=email, password_hash=hash_password("x"), role=UserRole.project_manager
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_reporting_employee(db, *, code, first_name, pm_id, user_id=None):
    from app.modules.employees.models import Employee, EmployeeStatus

    emp = Employee(
        employee_code=code,
        first_name=first_name,
        last_name="Test",
        user_id=user_id,
        reporting_pm_id=pm_id,
        status=EmployeeStatus.active,
        date_of_joining=date(2020, 1, 1),
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


def _make_report(db, *, employee_id, report_date, status):
    from app.modules.work_reports.models import DailyWorkReport

    report = DailyWorkReport(
        employee_id=employee_id, report_date=report_date, status=status
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def _collect(db, today=_THU):
    return DailyReportReminderService().collect(db, today=today)


def _missing_codes(reminders) -> set:
    return {e.code for r in reminders for e in r.employees}


# -- eligibility -------------------------------------------------------------


def test_employee_missing_the_previous_working_day_is_included(db):
    pm = _make_pm_user(db, "alex@example.com")
    _make_reporting_employee(db, code="EMP001", first_name="David", pm_id=pm.id)

    reminders = _collect(db)
    assert len(reminders) == 1
    assert reminders[0].report_date == _WED
    assert _missing_codes(reminders) == {"EMP001"}


def test_employee_who_submitted_the_previous_working_day_is_not_included(db):
    """Even though the employee never filed for 11 Aug or 10 Aug, only 12 Aug is
    checked — so they must not appear in the 13 Aug reminder."""
    from app.modules.work_reports.models import WorkReportStatus

    pm = _make_pm_user(db, "alex@example.com")
    emp = _make_reporting_employee(db, code="EMP001", first_name="David", pm_id=pm.id)
    _make_report(
        db, employee_id=emp.id, report_date=_WED, status=WorkReportStatus.submitted
    )

    assert _collect(db) == []


def test_older_missing_days_are_never_chased(db):
    """David missed 11 Aug but filed 12 Aug -> excluded. Erin missed 12 Aug ->
    included, and only for 12 Aug."""
    from app.modules.work_reports.models import WorkReportStatus

    pm = _make_pm_user(db, "alex@example.com")
    david = _make_reporting_employee(db, code="EMP001", first_name="David", pm_id=pm.id)
    _make_reporting_employee(db, code="EMP004", first_name="Erin", pm_id=pm.id)
    _make_report(
        db, employee_id=david.id, report_date=_WED, status=WorkReportStatus.submitted
    )

    reminders = _collect(db)
    assert _missing_codes(reminders) == {"EMP004"}
    assert reminders[0].report_date == _WED
    assert reminders[0].total_missing == 1


def test_granted_report_satisfies_the_target_day(db):
    """A report reopened for editing (status granted) is still recorded."""
    from app.modules.work_reports.models import WorkReportStatus

    pm = _make_pm_user(db, "alex@example.com")
    emp = _make_reporting_employee(db, code="EMP001", first_name="David", pm_id=pm.id)
    _make_report(
        db, employee_id=emp.id, report_date=_WED, status=WorkReportStatus.granted
    )

    assert _collect(db) == []


def test_draft_report_does_not_satisfy_the_target_day(db):
    from app.modules.work_reports.models import WorkReportStatus

    pm = _make_pm_user(db, "alex@example.com")
    emp = _make_reporting_employee(db, code="EMP001", first_name="David", pm_id=pm.id)
    _make_report(
        db, employee_id=emp.id, report_date=_WED, status=WorkReportStatus.draft
    )

    assert _missing_codes(_collect(db)) == {"EMP001"}


def test_collection_follows_the_calendar_when_the_previous_day_is_a_holiday(db):
    """12 Aug is a declared holiday, so 13 Aug chases 11 Aug instead."""
    from app.modules.work_reports.models import WorkReportStatus

    pm = _make_pm_user(db, "alex@example.com")
    _make_calendar_event(db, event_date=_WED, event_type="holiday", title="Festival")
    david = _make_reporting_employee(db, code="EMP001", first_name="David", pm_id=pm.id)
    _make_reporting_employee(db, code="EMP004", first_name="Erin", pm_id=pm.id)
    # David filed for the holiday but not for the real target day.
    _make_report(
        db, employee_id=david.id, report_date=_WED, status=WorkReportStatus.submitted
    )

    reminders = _collect(db)
    assert reminders[0].report_date == _TUE
    assert _missing_codes(reminders) == {"EMP001", "EMP004"}


def test_monday_run_chases_the_previous_friday(db):
    from app.modules.work_reports.models import WorkReportStatus

    pm = _make_pm_user(db, "alex@example.com")
    david = _make_reporting_employee(db, code="EMP001", first_name="David", pm_id=pm.id)
    _make_reporting_employee(db, code="EMP004", first_name="Erin", pm_id=pm.id)
    _make_report(
        db, employee_id=david.id, report_date=_PREV_FRI, status=WorkReportStatus.submitted
    )

    reminders = _collect(db, today=_MON)
    assert reminders[0].report_date == _PREV_FRI
    assert _missing_codes(reminders) == {"EMP004"}


def test_employee_who_had_not_joined_yet_is_not_chased(db):
    from app.modules.employees.models import Employee

    pm = _make_pm_user(db, "alex@example.com")
    emp = _make_reporting_employee(db, code="EMP001", first_name="David", pm_id=pm.id)
    db.execute(
        Employee.__table__.update()
        .where(Employee.id == emp.id)
        .values(date_of_joining=date(2026, 8, 13))
    )
    db.commit()

    assert _collect(db) == []


# -- PM exclusion (data layer) ----------------------------------------------


def test_pm_employees_are_excluded_from_rows_and_totals(db):
    """A user with the global project_manager role never owes a daily report.

    The exclusion must happen in the data layer, so employees_checked, the email
    rows and total_missing all agree.
    """
    from app.core.security import hash_password
    from app.modules.users.models import User, UserRole

    pm = _make_pm_user(db, "alex@example.com")
    _make_reporting_employee(db, code="EMP001", first_name="David", pm_id=pm.id)

    # A second PM who happens to report to Alex - excluded as a submitter.
    junior_pm_user = _make_pm_user(db, "bob@example.com")
    _make_reporting_employee(
        db, code="EMP002", first_name="Bob", pm_id=pm.id, user_id=junior_pm_user.id
    )

    # A normal employee WITH a login, and one with no login at all: both included.
    emp_user = User(
        email="carol@example.com",
        password_hash=hash_password("x"),
        role=UserRole.employee,
    )
    db.add(emp_user)
    db.commit()
    db.refresh(emp_user)
    _make_reporting_employee(
        db, code="EMP003", first_name="Carol", pm_id=pm.id, user_id=emp_user.id
    )
    _make_reporting_employee(db, code="EMP004", first_name="Erin", pm_id=pm.id)

    # Nobody submitted anything, so every checked employee owes the target day.
    reminders = _collect(db)
    assert len(reminders) == 1
    reminder = reminders[0]

    names = {e.name for e in reminder.employees}
    assert "Bob Test" not in names                    # the PM is gone
    assert {"David Test", "Carol Test", "Erin Test"} == names

    # 4 employees report to Alex, but only 3 are counted / rowed / totalled.
    assert reminder.employees_checked == 3
    assert reminder.total_missing == 3

    rendered = render_daily_report_reminder(reminder)
    assert "EMP002" not in rendered.html_body
    assert "EMP002" not in rendered.text_body
    csv_codes = [r["Employee ID"] for r in _csv_rows(rendered.csv_bytes)]
    assert sorted(csv_codes) == ["EMP001", "EMP003", "EMP004"]


def test_pm_remains_a_recipient_for_their_reporting_employees(db):
    """Excluded as a submitter, still emailed as a manager."""
    pm = _make_pm_user(db, "alex@example.com")
    _make_reporting_employee(
        db, code="EMP002", first_name="Bob", pm_id=pm.id, user_id=pm.id
    )
    _make_reporting_employee(db, code="EMP001", first_name="David", pm_id=pm.id)

    reminders = _collect(db)
    assert [r.pm_email for r in reminders] == ["alex@example.com"]
    assert reminders[0].employees_checked == 1
    assert _missing_codes(reminders) == {"EMP001"}


def test_pm_with_only_pm_reports_gets_no_email(db):
    """If every 'employee' under a PM is itself a PM, there is nothing to chase."""
    pm = _make_pm_user(db, "alex@example.com")
    junior = _make_pm_user(db, "bob@example.com")
    _make_reporting_employee(
        db, code="EMP002", first_name="Bob", pm_id=pm.id, user_id=junior.id
    )

    assert _collect(db) == []


# --- Celery task ------------------------------------------------------------


def test_celery_task_returns_summary_even_when_a_recipient_fails(monkeypatch):
    """The thin Celery task returns its summary dict (i.e. succeeds) when one
    recipient fails, because run_daily_report_reminders never re-raises."""
    from app.reminders.daily_report import dispatcher

    reminders = [_pm("ok@example.com"), _pm("broken@@invalid")]
    monkeypatch.setattr(
        dispatcher, "DailyReportReminderService", lambda *a, **k: _StubService(reminders)
    )
    monkeypatch.setattr(
        dispatcher,
        "EmailService",
        lambda *a, **k: _StubEmailService(bad_recipient="broken@@invalid"),
    )

    from app.tasks.periodic_tasks import send_daily_report_reminders

    summary = send_daily_report_reminders.run()  # call the task body directly
    assert summary == {
        "pms_with_missing": 2,
        "emails_sent": 1,
        "emails_skipped": 0,
        "emails_failed": 1,
        "total_missing": 2,
    }
