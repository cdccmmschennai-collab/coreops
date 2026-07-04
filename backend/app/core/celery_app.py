"""CoreOps Celery application + beat schedule.

Dedicated to CoreOps and independent of any other project's Celery setup. The
FastAPI backend never imports this module, so the API keeps working whether or
not the worker/beat processes are running.

Run:
  celery -A app.core.celery_app.celery_app worker --loglevel=info
  celery -A app.core.celery_app.celery_app beat   --loglevel=info

The reminder fires once daily at 09:30 Asia/Kolkata (see ScheduleSettings); the
hour/minute are overridable via environment.
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import settings

BUSINESS_TIMEZONE = "Asia/Kolkata"
DAILY_REPORT_REMINDER_TASK = "coreops.reminders.send_daily_report_reminders"


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


schedule_settings = ScheduleSettings()


def _build_schedule() -> dict:
    if not schedule_settings.REMINDER_SCHEDULE_ENABLED:
        return {}
    # Once daily at REMINDER_HOUR:REMINDER_MINUTE. Beat interprets this crontab in
    # celery_app.conf.timezone (= BUSINESS_TIMEZONE, Asia/Kolkata), so the default
    # 9/30 means 09:30 IST regardless of the server's local timezone.
    cron = crontab(
        hour=schedule_settings.REMINDER_HOUR,
        minute=schedule_settings.REMINDER_MINUTE,
    )
    return {
        "daily-report-reminder": {
            "task": DAILY_REPORT_REMINDER_TASK,
            "schedule": cron,
        }
    }


celery_app = Celery(
    "wms",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_BROKER_URL,
    include=["app.tasks.periodic_tasks"],
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
