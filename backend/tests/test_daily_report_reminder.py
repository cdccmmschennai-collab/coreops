"""Unit tests for the Daily Report Reminder — pure logic, no database.

Covers the working-day window (weekend skipping), the PM-exclusion rule, and
template / CSV rendering. The data collection against the DB is exercised via the
/debug endpoints and the dispatcher's own logging, per the phased testing plan.
"""
import csv
import io
import re
import uuid
from datetime import date, datetime

from app.notifications.email_service import EmailSendError
from app.reminders.daily_report.dispatcher import run_daily_report_reminders
from app.reminders.daily_report.service import (
    DEFAULT_LOOKBACK_WORKING_DAYS,
    DailyReportReminderService,
    MissingEmployee,
    MissingReportDay,
    PMReminder,
)
from app.reminders.daily_report.template import render_daily_report_reminder


def test_working_day_window_skips_weekends():
    svc = DailyReportReminderService()
    # Monday 2026-07-06 -> previous 3 working days must exclude Sat/Sun.
    window = svc.working_day_window(date(2026, 7, 6))
    assert len(window) == DEFAULT_LOOKBACK_WORKING_DAYS
    assert window == [
        date(2026, 7, 3),   # Fri
        date(2026, 7, 2),   # Thu
        date(2026, 7, 1),   # Wed
    ]
    # Most-recent first, strictly before the reference day, no weekends.
    assert window == sorted(window, reverse=True)
    assert all(d.weekday() < 5 for d in window)
    assert max(window) < date(2026, 7, 6)


def test_working_day_window_skips_weekend_when_reference_is_after_weekend():
    svc = DailyReportReminderService()
    # Monday reference: the 3 prior working days skip Sat/Sun entirely.
    window = svc.working_day_window(date(2026, 7, 6))
    assert date(2026, 7, 4) not in window  # Sat
    assert date(2026, 7, 5) not in window  # Sun


def _reminder() -> PMReminder:
    return PMReminder(
        pm_id=uuid.uuid4(),
        pm_name="Alex",
        pm_email="alex@example.com",
        employees_checked=3,
        days=[
            MissingReportDay(
                report_date=date(2026, 7, 3),
                employees=[
                    MissingEmployee(uuid.uuid4(), "John", "EMP002"),
                    MissingEmployee(uuid.uuid4(), "David", "EMP001"),
                ],
            ),
            MissingReportDay(
                report_date=date(2026, 7, 2),
                employees=[MissingEmployee(uuid.uuid4(), "David", "EMP001")],
            ),
        ],
    )


def test_subject_contains_the_generated_date():
    rendered = render_daily_report_reminder(
        _reminder(), now=datetime(2026, 7, 9, 17, 15)
    )
    assert rendered.subject == "CoreOps | Outstanding Daily Reports | 09 Jul 2026"


def test_template_text_layout_has_four_columns_and_summary():
    rendered = render_daily_report_reminder(
        _reminder(), now=datetime(2026, 7, 6, 9, 30)
    )
    text = rendered.text_body
    assert text.startswith("CoreOps\nDaily Reporting Compliance")
    assert "Hello Alex," in text
    assert (
        "The following employees have outstanding daily work reports as of "
        "06 Jul 2026, 09:30 AM IST." in text
    )
    # The same four columns as the HTML and the CSV.
    for header in ("Employee ID", "Employee Name", "Missing Days", "Missing Report Dates"):
        assert header in text
    # Code and name are separate cells, not "EMP001 David". Cells are padded to
    # the column width, so match the pipes rather than exact spacing.
    assert "EMP001 David" not in text
    assert re.search(r"\|\s*EMP001\s*\|\s*David\s*\|\s*2\s*\|", text)
    assert re.search(r"\|\s*EMP002\s*\|\s*John\s*\|\s*1\s*\|", text)
    assert "02 Jul • 03 Jul" in text  # David's two dates, bullet-separated
    assert text.index("David") < text.index("John")  # sorted by name
    assert "Employees with Missing Reports: 2" in text
    assert "Total Missing Report Days: 3" in text
    assert "attached as a CSV file" in text
    assert text.rstrip().endswith("Automated notification - please do not reply.")


def test_plain_text_fallback_has_no_html_css_or_urls():
    text = render_daily_report_reminder(_reminder()).text_body
    for token in ("<", ">", "http", "style=", "padding:", "Content-Type"):
        assert token not in text


def test_template_html_columns_summary_and_greeting():
    html = render_daily_report_reminder(
        _reminder(), now=datetime(2026, 7, 6, 9, 30)
    ).html_body
    assert "Hello Alex" in html
    assert "Daily Reporting Compliance" in html
    for header in ("Employee ID", "Employee Name", "Missing Days", "Missing Report Dates"):
        assert header in html
    # Employee code and name land in separate cells.
    assert '>EMP001</td><td style="' in html.replace("\n", "")
    assert ">David</td>" in html and ">John</td>" in html
    # Dates bullet-separated, not stuck together.
    assert "02 Jul • 03 Jul" in html
    assert "02 Jul03 Jul" not in html
    assert "Employees with Missing Reports: <strong>2</strong>" in html
    assert "Total Missing Report Days: <strong>3</strong>" in html
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


def test_missing_days_count_matches_the_dates_listed():
    rendered = render_daily_report_reminder(_reminder())
    rows = _csv_rows(rendered.csv_bytes)
    by_code = {r["Employee ID"]: r for r in rows}
    assert by_code["EMP001"]["Missing Days"] == "2"   # David: 02 + 03 Jul
    assert by_code["EMP002"]["Missing Days"] == "1"   # John: 03 Jul
    for row in rows:
        assert int(row["Missing Days"]) == len(row["Missing Report Dates"].split(","))


# --- CSV attachment ---------------------------------------------------------


def _csv_rows(csv_bytes: bytes) -> list[dict]:
    """Decode the attachment the way Excel does and parse it as CSV."""
    text = csv_bytes.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def test_csv_filename_uses_the_generated_date():
    rendered = render_daily_report_reminder(
        _reminder(), now=datetime(2026, 7, 9, 17, 15)
    )
    assert rendered.csv_filename == "coreops_outstanding_reports_2026-07-09.csv"


def test_csv_is_valid_comma_separated_content_with_bom_and_crlf():
    rendered = render_daily_report_reminder(_reminder())
    raw = rendered.csv_bytes
    # Excel needs the BOM to decode UTF-8 (the bullet in the HTML body, non-ASCII
    # employee names) instead of falling back to the local ANSI code page.
    assert raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in raw
    text = raw.decode("utf-8-sig")
    assert text.splitlines()[0] == (
        "Employee ID,Employee Name,Missing Days,Missing Report Dates"
    )
    rows = _csv_rows(raw)
    assert len(rows) == 2
    assert [r["Employee ID"] for r in rows] == ["EMP001", "EMP002"]
    # Multiple dates stay in ONE quoted cell, comma-separated.
    assert '"02 Jul, 03 Jul"' in text
    assert rows[0]["Missing Report Dates"] == "02 Jul, 03 Jul"


def test_csv_contains_only_the_recipient_pms_employees():
    mine = PMReminder(
        pm_id=uuid.uuid4(),
        pm_name="Alex",
        pm_email="alex@example.com",
        employees_checked=1,
        days=[
            MissingReportDay(
                report_date=date(2026, 7, 3),
                employees=[MissingEmployee(uuid.uuid4(), "David", "EMP001")],
            )
        ],
    )
    rows = _csv_rows(render_daily_report_reminder(mine).csv_bytes)
    assert [r["Employee Name"] for r in rows] == ["David"]
    # An employee from another PM's group ("John"/EMP002) never leaks in.
    assert all("John" not in r["Employee Name"] for r in rows)
    assert all(r["Employee ID"] != "EMP002" for r in rows)


def test_total_missing_counts_all_employees_across_days():
    assert _reminder().total_missing == 3


# --- Failure isolation: one bad recipient must not stop the others ----------


def _pm(email: str) -> PMReminder:
    return PMReminder(
        pm_id=uuid.uuid4(),
        pm_name=email.split("@")[0],
        pm_email=email,
        employees_checked=1,
        days=[
            MissingReportDay(
                report_date=date(2026, 7, 3),
                employees=[MissingEmployee(uuid.uuid4(), "John")],
            )
        ],
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


# --- PM exclusion (data layer, against the real DB) -------------------------


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

    # Nobody submitted anything, so every checked employee owes the full window.
    reminders = DailyReportReminderService().collect(db, today=date(2026, 7, 6))
    assert len(reminders) == 1
    reminder = reminders[0]

    names = {e.name for day in reminder.days for e in day.employees}
    assert "Bob Test" not in names                    # the PM is gone
    assert {"David Test", "Carol Test", "Erin Test"} <= names

    # 4 employees report to Alex, but only 3 are counted / rowed / totalled.
    assert reminder.employees_checked == 3
    assert reminder.total_missing == 3 * DEFAULT_LOOKBACK_WORKING_DAYS

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

    reminders = DailyReportReminderService().collect(db, today=date(2026, 7, 6))
    assert [r.pm_email for r in reminders] == ["alex@example.com"]
    assert reminders[0].employees_checked == 1


def test_pm_with_only_pm_reports_gets_no_email(db):
    """If every 'employee' under a PM is itself a PM, there is nothing to chase."""
    pm = _make_pm_user(db, "alex@example.com")
    junior = _make_pm_user(db, "bob@example.com")
    _make_reporting_employee(
        db, code="EMP002", first_name="Bob", pm_id=pm.id, user_id=junior.id
    )

    assert DailyReportReminderService().collect(db, today=date(2026, 7, 6)) == []


# --- Recorded-status rule: submitted OR granted satisfies a day; drafts and
# --- task-completion state never do (against the real DB) ------------------


def _make_report(db, *, employee_id, report_date, status):
    from app.modules.work_reports.models import DailyWorkReport

    report = DailyWorkReport(
        employee_id=employee_id, report_date=report_date, status=status
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def _make_two_day_task_item(db, *, employee_id, started_on, target_days=2, completed_on=None):
    """An open (or completed) TASK_BASED WorkItem spanning `target_days`.

    The reminder must never consult this: it exists only to prove that an
    in-flight multi-day task neither auto-satisfies a later day nor is required
    for an earlier submitted day to count.
    """
    from app.modules.activity_master.models import ActivityMaster
    from app.modules.projects.models import Project, ProjectStatus
    from app.modules.work_reports.models import WorkItem
    from app.modules.work_reports.work_items import compute_due_date

    project = Project(
        code=f"PRJ-{uuid.uuid4().hex[:8]}", name="Task Project", status=ProjectStatus.planning
    )
    sub_activity = ActivityMaster(
        name="Two-day task", level="sub_activity", benchmark_type="TASK_BASED"
    )
    db.add_all([project, sub_activity])
    db.commit()
    db.refresh(project)
    db.refresh(sub_activity)

    item = WorkItem(
        employee_id=employee_id,
        project_id=project.id,
        sub_activity_id=sub_activity.id,
        started_on=started_on,
        target_days=target_days,
        due_date=compute_due_date(started_on, target_days),
        completed_on=completed_on,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _missing_dates_for(reminders, employee_id) -> set:
    return {
        day.report_date
        for r in reminders
        for day in r.days
        for e in day.employees
        if e.employee_id == employee_id
    }


# Monday reference -> window is Fri 03 / Thu 02 / Wed 01 Jul 2026.
_TODAY = date(2026, 7, 6)
_DAY1 = date(2026, 7, 1)   # task start
_DAY2 = date(2026, 7, 2)   # task due date
_DAY3 = date(2026, 7, 3)   # unrelated working day


def _collect(db):
    return DailyReportReminderService().collect(db, today=_TODAY)


def test_submitted_day1_of_open_two_day_task_is_not_missing_for_day1(db):
    """Day 1 submitted, task not marked complete (WorkItem open, completed_on
    NULL): Day 1 is recorded. Day 2, with no continuation report, is missing."""
    from app.modules.work_reports.models import WorkReportStatus

    pm = _make_pm_user(db, "alex@example.com")
    emp = _make_reporting_employee(db, code="EMP001", first_name="David", pm_id=pm.id)
    _make_two_day_task_item(db, employee_id=emp.id, started_on=_DAY1)
    _make_report(db, employee_id=emp.id, report_date=_DAY1, status=WorkReportStatus.submitted)

    missing = _missing_dates_for(_collect(db), emp.id)
    assert _DAY1 not in missing            # submitted, despite the open task
    assert _DAY2 in missing                # no continuation report yet
    assert _DAY3 in missing                # unrelated day, never reported


def test_any_submitted_report_on_day2_records_day2_regardless_of_activity(db):
    """Day 2 is recorded by ANY submitted report, whether it continues the open
    two-day task or logs a completely different activity. The reminder never
    inspects the activity, the WorkItem, or the completion checkbox — a Day 2
    report is not mandatory to be a continuation of Day 1's task."""
    from app.modules.work_reports.models import WorkReportStatus

    pm = _make_pm_user(db, "alex@example.com")
    emp = _make_reporting_employee(db, code="EMP001", first_name="David", pm_id=pm.id)
    # Day 1's two-day task stays open (completed_on NULL) the whole time.
    _make_two_day_task_item(db, employee_id=emp.id, started_on=_DAY1)
    _make_report(db, employee_id=emp.id, report_date=_DAY1, status=WorkReportStatus.submitted)
    # Day 2: a submitted report for a *different* activity — still records Day 2.
    _make_report(db, employee_id=emp.id, report_date=_DAY2, status=WorkReportStatus.submitted)

    missing = _missing_dates_for(_collect(db), emp.id)
    assert _DAY1 not in missing
    assert _DAY2 not in missing            # any submitted report records the day
    assert _DAY3 in missing


def test_granted_report_satisfies_its_date(db):
    """A report reopened for editing (status granted) is still recorded."""
    from app.modules.work_reports.models import WorkReportStatus

    pm = _make_pm_user(db, "alex@example.com")
    emp = _make_reporting_employee(db, code="EMP001", first_name="David", pm_id=pm.id)
    _make_report(db, employee_id=emp.id, report_date=_DAY2, status=WorkReportStatus.granted)

    missing = _missing_dates_for(_collect(db), emp.id)
    assert _DAY2 not in missing
    assert missing == {_DAY1, _DAY3}


def test_draft_report_does_not_satisfy_its_date(db):
    """A draft is not a recorded report; the day stays missing."""
    from app.modules.work_reports.models import WorkReportStatus

    pm = _make_pm_user(db, "alex@example.com")
    emp = _make_reporting_employee(db, code="EMP001", first_name="David", pm_id=pm.id)
    _make_report(db, employee_id=emp.id, report_date=_DAY2, status=WorkReportStatus.draft)

    missing = _missing_dates_for(_collect(db), emp.id)
    assert _DAY2 in missing
    assert missing == {_DAY1, _DAY2, _DAY3}


def test_unreported_working_days_all_remain_missing(db):
    """Baseline: with no reports at all, every window day is chased."""
    pm = _make_pm_user(db, "alex@example.com")
    emp = _make_reporting_employee(db, code="EMP001", first_name="David", pm_id=pm.id)

    missing = _missing_dates_for(_collect(db), emp.id)
    assert missing == {_DAY1, _DAY2, _DAY3}


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
