"""Daily report reminder orchestration (service -> template -> email).

This is the application layer that composes the pure data service, the template,
and the EmailService. It owns the "one email per PM, skip empty, keep going on
failure" policy and the structured run logging. The Celery task is a one-liner
that calls :func:`run_daily_report_reminders`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.notifications.email_service import Attachment, EmailSendError, EmailService
from app.reminders.daily_report.service import DailyReportReminderService
from app.reminders.daily_report.template import render_daily_report_reminder

logger = logging.getLogger("coreops.reminders.daily_report")


@dataclass
class PMOutcome:
    pm_email: str
    employees_checked: int
    missing_found: int
    email_sent: bool
    error: str | None = None


@dataclass
class ReminderRunResult:
    pms_with_missing: int = 0
    emails_sent: int = 0
    emails_skipped: int = 0
    emails_failed: int = 0
    total_missing: int = 0
    outcomes: list[PMOutcome] = field(default_factory=list)


def run_daily_report_reminders(
    *,
    db: Session | None = None,
    email_service: EmailService | None = None,
    service: DailyReportReminderService | None = None,
    today: date | None = None,
) -> ReminderRunResult:
    """Collect missing reports and email each affected PM.

    Safe to call from a Celery worker (manages its own session when ``db`` is not
    supplied) or from a request handler (pass the request session). One PM's email
    failure never aborts the run.
    """
    owns_session = db is None
    db = db or SessionLocal()
    service = service or DailyReportReminderService()
    email_service = email_service or EmailService()
    result = ReminderRunResult()

    logger.info("reminder.started job=daily_report_reminder")
    try:
        reminders = service.collect(db, today=today)
        result.pms_with_missing = len(reminders)
        logger.info("reminder.collected pms_with_missing=%d", len(reminders))

        for reminder in reminders:
            outcome = _process_pm(reminder, email_service)
            result.outcomes.append(outcome)
            result.total_missing += outcome.missing_found
            if outcome.error is not None:
                result.emails_failed += 1
            elif outcome.email_sent:
                result.emails_sent += 1
            else:
                result.emails_skipped += 1
    finally:
        if owns_session:
            db.close()

    logger.info(
        "reminder.completed job=daily_report_reminder pms=%d sent=%d skipped=%d "
        "failed=%d missing=%d",
        result.pms_with_missing,
        result.emails_sent,
        result.emails_skipped,
        result.emails_failed,
        result.total_missing,
    )
    return result


def _process_pm(reminder, email_service: EmailService) -> PMOutcome:
    logger.info(
        "reminder.pm pm=%s employees_checked=%d missing_found=%d",
        reminder.pm_email,
        reminder.employees_checked,
        reminder.total_missing,
    )
    # Belt-and-braces: the service already filters out PMs with no missing days.
    if reminder.total_missing == 0:
        return PMOutcome(
            pm_email=reminder.pm_email,
            employees_checked=reminder.employees_checked,
            missing_found=0,
            email_sent=False,
        )

    try:
        rendered = render_daily_report_reminder(reminder)
        # Built from this PM's own reminder rows, so the CSV can never contain
        # another PM's reporting employees.
        sent = email_service.send(
            to=reminder.pm_email,
            subject=rendered.subject,
            html_body=rendered.html_body,
            text_body=rendered.text_body,
            attachments=[
                Attachment(
                    filename=rendered.csv_filename,
                    content=rendered.csv_bytes,
                    maintype="text",
                    subtype="csv",
                )
            ],
        )
        logger.info(
            "reminder.email_sent pm=%s sent=%s missing=%d",
            reminder.pm_email,
            sent,
            reminder.total_missing,
        )
        return PMOutcome(
            pm_email=reminder.pm_email,
            employees_checked=reminder.employees_checked,
            missing_found=reminder.total_missing,
            email_sent=sent,
        )
    except EmailSendError as exc:
        # One PM failing must not stop the rest of the run.
        logger.error("reminder.email_failed pm=%s error=%s", reminder.pm_email, exc)
        return PMOutcome(
            pm_email=reminder.pm_email,
            employees_checked=reminder.employees_checked,
            missing_found=reminder.total_missing,
            email_sent=False,
            error=str(exc),
        )
    except Exception as exc:  # noqa: BLE001 - last-resort isolation per PM
        logger.exception("reminder.pm_unexpected_error pm=%s", reminder.pm_email)
        return PMOutcome(
            pm_email=reminder.pm_email,
            employees_checked=reminder.employees_checked,
            missing_found=reminder.total_missing,
            email_sent=False,
            error=str(exc),
        )
