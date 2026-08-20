"""Scheduled Celery tasks.

Each task is a thin trigger — it delegates immediately to an application service
and does no business logic, SQL, SMTP, or templating of its own.
"""
from __future__ import annotations

from app.core.celery_app import (
    DAILY_REPORT_REMINDER_TASK,
    LEAVE_BALANCE_NOTICE_TASK,
    celery_app,
)
from app.reminders.daily_report.dispatcher import run_daily_report_reminders
from app.reminders.leave_balance.dispatcher import run_monthly_leave_balance_notices


@celery_app.task(name=DAILY_REPORT_REMINDER_TASK)
def send_daily_report_reminders() -> dict:
    """Trigger the daily missing-report reminder run. Returns a small summary."""
    result = run_daily_report_reminders()
    return {
        "pms_with_missing": result.pms_with_missing,
        "emails_sent": result.emails_sent,
        "emails_skipped": result.emails_skipped,
        "emails_failed": result.emails_failed,
        "total_missing": result.total_missing,
    }


@celery_app.task(name=LEAVE_BALANCE_NOTICE_TASK)
def send_monthly_leave_balance_notices() -> dict:
    """Tell each eligible employee this month's leave balance. Idempotent: the
    run after the first one in a month sends nothing."""
    result = run_monthly_leave_balance_notices()
    return {
        "month": result.month.isoformat(),
        "eligible": result.eligible,
        "sent": result.sent,
        "already_sent": result.already_sent,
        "failed": result.failed,
    }
