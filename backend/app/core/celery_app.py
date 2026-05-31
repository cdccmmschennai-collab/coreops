"""Celery application.

Present per the approved stack. No tasks are defined in V0; background jobs
(if any) arrive in later phases. The broker is Redis (separate logical DB).
"""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "wms",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_BROKER_URL,
)
celery_app.conf.update(
    task_track_started=True,
    task_default_queue="wms",
)
