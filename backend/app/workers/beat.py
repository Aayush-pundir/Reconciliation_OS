"""Celery-beat periodic task: fires due RecurringSchedules by re-queuing
their source run's exact input file set (the same mechanics as the manual
POST /api/runs/{run_id}/rerun endpoint), then records when it last fired.

Registered on celery_app's beat_schedule - started via:
  celery -A app.workers.celery_app beat --loglevel=info
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal
from app.core.job_runner import get_job_runner
from app.models import RecurringSchedule, Run, RunFile
from app.workers.celery_app import celery_app


def _is_due(schedule: RecurringSchedule, now: datetime) -> bool:
    if schedule.last_fired_at is None:
        return True
    last_fired = schedule.last_fired_at
    if last_fired.tzinfo is None:
        # SQLite's DateTime(timezone=True) doesn't actually preserve tzinfo
        # on read-back (unlike Postgres) - values written as UTC come back
        # naive, so assume UTC rather than crash comparing aware vs naive.
        last_fired = last_fired.replace(tzinfo=timezone.utc)
    return now - last_fired >= timedelta(minutes=schedule.interval_minutes)


@celery_app.task(name="recon_os.check_recurring_schedules")
def check_recurring_schedules() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        schedules = db.query(RecurringSchedule).filter(RecurringSchedule.enabled.is_(True)).all()
        for schedule in schedules:
            if not _is_due(schedule, now):
                continue

            source = db.get(Run, schedule.source_run_id)
            if source is None or source.status != "completed":
                continue

            new_run = Run(
                module_key=source.module_key, status="queued",
                triggered_by=source.triggered_by, options=source.options,
            )
            db.add(new_run)
            db.commit()

            for f in db.query(RunFile).filter(RunFile.run_id == source.id).all():
                db.add(
                    RunFile(
                        run_id=new_run.id, slot=f.slot, original_filename=f.original_filename,
                        content_hash=f.content_hash, size_bytes=f.size_bytes,
                        storage_path=f.storage_path, validation_ok=f.validation_ok,
                    )
                )
            db.commit()

            get_job_runner().enqueue(new_run.id)

            schedule.last_fired_at = now
            schedule.last_run_id = new_run.id
            db.add(schedule)
            db.commit()
    finally:
        db.close()
