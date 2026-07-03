"""CoreOps Celery application + beat schedule.

Dedicated to CoreOps and independent of any other project's Celery setup. The
FastAPI backend never imports this module, so the API keeps working whether or
not the worker/beat processes are running.

Run:
  celery -A app.core.celery_app.celery_app worker --loglevel=info
  celery -A app.core.celery_app.celery_app beat   --loglevel=info

The schedule is configurable via environment so it can fire every minute during
testing, then be set to 09:30 Asia/Kolkata for production (see ScheduleSettings).
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

    During development set REMINDER_EVERY_MINUTE=true to fire every minute; for
    production leave it false and use REMINDER_HOUR / REMINDER_MINUTE (09:30 IST).
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    REMINDER_SCHEDULE_ENABLED: bool = True
    REMINDER_EVERY_MINUTE: bool = False
    REMINDER_HOUR: int = 9
    REMINDER_MINUTE: int = 30


schedule_settings = ScheduleSettings()


def _build_schedule() -> dict:
    if not schedule_settings.REMINDER_SCHEDULE_ENABLED:
        return {}
    if schedule_settings.REMINDER_EVERY_MINUTE:
        cron = crontab()  # every minute — testing only
    else:
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
