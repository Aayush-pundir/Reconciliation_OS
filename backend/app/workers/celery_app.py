"""Celery application - the production JobRunner backend (ARCHITECTURE.md
§4.2, §Deployment Topology). Started via:
  celery -A app.workers.celery_app worker --loglevel=info
"""
from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "recon_os",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks", "app.workers.beat"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        # Polls every 60s for due RecurringSchedules (see app/workers/beat.py).
        # Poll frequency is independent of any individual schedule's own
        # interval_minutes - it's just how often we check what's due.
        "check-recurring-schedules": {"task": "recon_os.check_recurring_schedules", "schedule": 60.0},
    },
)
