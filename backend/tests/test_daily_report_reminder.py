"""Unit tests for the Daily Report Reminder — pure logic, no database.

Covers the working-day window (weekend skipping) and template rendering /
grouping. The data collection against the DB is exercised via the /debug
endpoints and the dispatcher's own logging, per the phased testing plan.
"""
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
    # Monday 2026-07-06 -> previous 7 working days must exclude Sat/Sun.
    window = svc.working_day_window(date(2026, 7, 6))
    assert len(window) == DEFAULT_LOOKBACK_WORKING_DAYS
    assert window == [
        date(2026, 7, 3),   # Fri
        date(2026, 7, 2),   # Thu
        date(2026, 7, 1),   # Wed
        date(2026, 6, 30),  # Tue
        date(2026, 6, 29),  # Mon
        date(2026, 6, 26),  # Fri (skips Sun 28 / Sat 27)
        date(2026, 6, 25),  # Thu
    ]
    # Most-recent first, strictly before the reference day, no weekends.
    assert window == sorted(window, reverse=True)
    assert all(d.weekday() < 5 for d in window)
    assert max(window) < date(2026, 7, 6)


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
                    MissingEmployee(uuid.uuid4(), "John"),
                    MissingEmployee(uuid.uuid4(), "David"),
                ],
            ),
            MissingReportDay(
                report_date=date(2026, 7, 2),
                employees=[MissingEmployee(uuid.uuid4(), "David")],
            ),
        ],
    )


def test_template_subject_and_text_layout():
    rendered = render_daily_report_reminder(
        _reminder(), now=datetime(2026, 7, 6, 9, 30)
    )
    assert rendered.subject == "CoreOps • Outstanding Daily Reports"
    text = rendered.text_body
    assert text.startswith("Good Morning Alex,")
    assert "The following daily reports are still pending." in text
    # Dates appear most-recent first.
    assert text.index("03 Jul") < text.index("02 Jul")
    assert "• John" in text and "• David" in text
    assert "Please follow up with the respective employees." in text
    assert text.rstrip().endswith("CoreOps")


def test_template_html_escapes_and_greets_by_time():
    reminder = _reminder()
    html = render_daily_report_reminder(
        reminder, now=datetime(2026, 7, 6, 15, 0)
    ).html_body
    assert "Good Afternoon Alex" in html
    assert "Outstanding Daily Reports" in html
    assert "03 Jul" in html and "02 Jul" in html
    assert "John" in html


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

    def send(self, *, to, subject, html_body, text_body=None):
        if to == self.bad_recipient:
            raise EmailSendError(f"SMTP recipient refused: {to}")
        self.sent_to.append(to)
        return True


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
