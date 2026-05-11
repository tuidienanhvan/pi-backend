"""Celery app — background tasks (bulk AI, email, cleanup)."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "pi_backend",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.shared.tasks", "app.celery_tasks.token_reset"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    broker_connection_retry_on_startup=True,
)

celery_app.conf.beat_schedule = {
    "daily-token-reset": {
        "task": "token_reset.daily_check",
        "schedule": crontab(hour=0, minute=5),
    },
}
