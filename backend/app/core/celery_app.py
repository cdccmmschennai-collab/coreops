"""CoreOps Celery application + beat schedule.

Dedicated to CoreOps and independent of any other project's Celery setup. The
FastAPI backend never imports this module, so the API keeps working whether or
not the worker/beat processes are running.

Run:
  celery -A app.core.celery_app.celery_app worker --loglevel=info
  celery -A app.core.celery_app.celery_app beat   --loglevel=info

The reminder fires once daily at 09:30 Asia/Kolkata (see ScheduleSettings); the
hour/minute are overridable via environment.

The monthly leave balance notice is registered on the SAME beat - CoreOps has one
scheduler and this phase did not add a second. It is also fired DAILY rather than
on the 1st: the job is idempotent per (employee, month), so the first run of a
month sends and the rest of the month is a no-op, while a worker that was down on
the 1st still delivers on the 2nd. See
`app/reminders/leave_balance/dispatcher.py`.

Automatic report generation - week-off reports on closed days and leave reports
on the working days an approved leave covers - shares the same beat and the same
reasoning, for the same reason again: it is idempotent per (employee, date), so
it runs every morning and re-sweeps the days behind it rather than depending on
one fragile midnight execution. Both sweeps hang off the one task; see
`app/modules/work_reports/auto_reports.py`.
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import settings

BUSINESS_TIMEZONE = "Asia/Kolkata"
DAILY_REPORT_REMINDER_TASK = "coreops.reminders.send_daily_report_reminders"
LEAVE_BALANCE_NOTICE_TASK = "coreops.reminders.send_monthly_leave_balance_notices"
# Automatic report generation - week-off AND leave sweeps, one task
# (app/modules/work_reports/auto_reports.py).
AUTO_REPORT_GENERATION_TASK = "coreops.work_reports.generate_auto_reports"
# Generic "deliver one email" task (app/tasks/email_tasks.py). NOT scheduled -
# it is fired on demand by app.notifications.email_dispatch.enqueue_email, so it
# appears in `include` below but never in the beat schedule.
EMAIL_SEND_TASK = "coreops.notifications.send_email"


class ScheduleSettings(BaseSettings):
    """Beat scheduling knobs, from environment.

    The reminder runs once per day at REMINDER_HOUR:REMINDER_MINUTE in the app's
    business timezone (Asia/Kolkata). Defaults are 09:30 IST; override the hour /
    minute via environment if needed. Set REMINDER_SCHEDULE_ENABLED=false to
    register no schedule at all.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    REMINDER_SCHEDULE_ENABLED: bool = True
    REMINDER_HOUR: int = 9
    REMINDER_MINUTE: int = 30

    # The monthly leave balance notice. Its own flag and its own time, so it can
    # be turned off or moved without touching the daily report reminder.
    LEAVE_BALANCE_NOTICE_ENABLED: bool = True
    LEAVE_BALANCE_NOTICE_HOUR: int = 8
    LEAVE_BALANCE_NOTICE_MINUTE: int = 0

    # Automatic week-off report generation. Early morning IST so a weekend day
    # is filed on the day itself, and its own flag/time like every other entry.
    # AUTO_REPORT_LOOKBACK_DAYS is the self-healing margin, not a catch-up
    # window: the job is idempotent, so re-sweeping covered dates writes
    # nothing and a worker that was down simply catches up on its next run.
    AUTO_REPORT_GENERATION_ENABLED: bool = True
    AUTO_REPORT_HOUR: int = 1
    AUTO_REPORT_MINUTE: int = 0
    AUTO_REPORT_LOOKBACK_DAYS: int = 7


schedule_settings = ScheduleSettings()


def _build_schedule() -> dict:
    """The beat entries, each behind its own flag.

    Every crontab here is interpreted in celery_app.conf.timezone
    (= BUSINESS_TIMEZONE, Asia/Kolkata), so the hours below mean IST regardless of
    the server's local timezone.
    """
    schedule: dict = {}

    if schedule_settings.REMINDER_SCHEDULE_ENABLED:
        # Once daily at REMINDER_HOUR:REMINDER_MINUTE (default 09:30 IST).
        schedule["daily-report-reminder"] = {
            "task": DAILY_REPORT_REMINDER_TASK,
            "schedule": crontab(
                hour=schedule_settings.REMINDER_HOUR,
                minute=schedule_settings.REMINDER_MINUTE,
            ),
        }

    if schedule_settings.LEAVE_BALANCE_NOTICE_ENABLED:
        # Daily, not monthly - the task is idempotent per (employee, month), so
        # this sends once per employee per month and self-heals a missed 1st.
        schedule["monthly-leave-balance-notice"] = {
            "task": LEAVE_BALANCE_NOTICE_TASK,
            "schedule": crontab(
                hour=schedule_settings.LEAVE_BALANCE_NOTICE_HOUR,
                minute=schedule_settings.LEAVE_BALANCE_NOTICE_MINUTE,
            ),
        }

    if schedule_settings.AUTO_REPORT_GENERATION_ENABLED:
        # Daily, on the same beat, for the same reason the leave notice is daily:
        # the run is idempotent, so firing it every morning files today's weekend
        # report and re-covers the days behind it at the cost of one SELECT each.
        schedule["auto-report-generation"] = {
            "task": AUTO_REPORT_GENERATION_TASK,
            "schedule": crontab(
                hour=schedule_settings.AUTO_REPORT_HOUR,
                minute=schedule_settings.AUTO_REPORT_MINUTE,
            ),
        }

    return schedule


celery_app = Celery(
    "wms",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_BROKER_URL,
    # Every module holding a @celery_app.task MUST be listed here - the worker
    # imports exactly these, and a task in an unlisted module is never
    # registered, so calls to it die as "Received unregistered task".
    include=["app.tasks.periodic_tasks", "app.tasks.email_tasks"],
)
celery_app.conf.update(
    task_track_started=True,
    task_default_queue="wms",
    timezone=BUSINESS_TIMEZONE,
    enable_utc=True,
    task_acks_late=True,
    worker_hijack_root_logger=False,
    beat_schedule=_build_schedule(),
)
