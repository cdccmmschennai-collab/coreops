"""Scheduled Celery tasks.

Each task is a thin trigger — it delegates immediately to an application service
and does no business logic, SQL, SMTP, or templating of its own.
"""
from __future__ import annotations

from app.core.celery_app import (
    AUTO_REPORT_GENERATION_TASK,
    DAILY_REPORT_REMINDER_TASK,
    LEAVE_BALANCE_NOTICE_TASK,
    celery_app,
    schedule_settings,
)
from app.modules.work_reports.auto_reports import (
    generate_auto_leave_reports,
    generate_auto_reports,
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


@celery_app.task(name=AUTO_REPORT_GENERATION_TASK)
def generate_automatic_reports() -> dict:
    """File the automatic reports for every recent day that accounts for itself:
    a week-off report for everybody on a closed day, and a leave report for
    everybody an approved leave covers on an open one.

    Two sweeps, one task and one beat entry, because they are the same job read
    from opposite sides of the calendar and can never both claim a date. Both are
    idempotent, so a date already covered produces nothing and running this late,
    twice, or after a failed run is harmless.

    The leave sweep runs SECOND and on its own session, so a failure in it cannot
    lose the week-off reports the first sweep already committed.
    """
    result = generate_auto_reports(
        lookback_days=schedule_settings.AUTO_REPORT_LOOKBACK_DAYS
    )
    leave = generate_auto_leave_reports(
        lookback_days=schedule_settings.AUTO_REPORT_LOOKBACK_DAYS
    )
    return {
        "dates": len(result.dates),
        "working_dates": result.working_dates,
        "employees_considered": result.employees_considered,
        "created": result.created,
        "skipped_existing": result.skipped_existing,
        "failed": result.failed,
        "leave_employees_considered": leave.employees_considered,
        "leave_created": leave.created,
        "leave_skipped_existing": leave.skipped_existing,
        "leave_failed": leave.failed,
    }
