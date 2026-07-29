"""Celery-beat recurring-schedule logic (app/workers/beat.py). Exercises
check_recurring_schedules() directly rather than through Celery's task
machinery - it's a plain function under the @celery_app.task decorator,
callable synchronously in tests."""
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")

from app.core.database import Base, SessionLocal, engine
from app.models import RecurringSchedule, Run, RunFile
from app.workers.beat import check_recurring_schedules


def setup_module() -> None:
    Base.metadata.create_all(bind=engine)


def _make_completed_run(db, module_key: str = "fake_test_module") -> Run:
    run = Run(module_key=module_key, status="completed", options={"threshold": 1})
    db.add(run)
    db.commit()
    db.add(
        RunFile(
            run_id=run.id, slot="f", original_filename="a.xlsx", content_hash="deadbeef",
            size_bytes=10, storage_path=f"runs/{run.id}/f/a.xlsx", validation_ok=True,
        )
    )
    db.commit()
    db.refresh(run)
    return run


def test_due_schedule_fires_and_clones_source_run(monkeypatch):
    enqueued: list[str] = []
    monkeypatch.setattr(
        "app.workers.beat.get_job_runner",
        lambda: type("FakeRunner", (), {"enqueue": staticmethod(lambda run_id: enqueued.append(str(run_id)))})(),
    )

    db = SessionLocal()
    source = _make_completed_run(db)
    source_id, source_module_key = source.id, source.module_key
    schedule = RecurringSchedule(
        name="nightly", module_key=source.module_key, source_run_id=source.id,
        interval_minutes=60, enabled=True, last_fired_at=None,
    )
    db.add(schedule)
    db.commit()
    schedule_id = schedule.id
    db.close()

    check_recurring_schedules()

    db = SessionLocal()
    refreshed = db.get(RecurringSchedule, schedule_id)
    assert refreshed.last_fired_at is not None
    assert refreshed.last_run_id is not None

    new_run = db.get(Run, refreshed.last_run_id)
    assert new_run.status == "queued"
    assert new_run.module_key == source_module_key
    assert new_run.options == {"threshold": 1}

    cloned_files = db.query(RunFile).filter(RunFile.run_id == new_run.id).all()
    assert len(cloned_files) == 1
    assert cloned_files[0].original_filename == "a.xlsx"
    assert cloned_files[0].run_id != source_id  # a genuinely new RunFile row, not the same one

    assert len(enqueued) == 1
    assert enqueued[0] == new_run.id
    db.close()


def test_not_yet_due_schedule_does_not_fire(monkeypatch):
    enqueued: list[str] = []
    monkeypatch.setattr(
        "app.workers.beat.get_job_runner",
        lambda: type("FakeRunner", (), {"enqueue": staticmethod(lambda run_id: enqueued.append(str(run_id)))})(),
    )

    db = SessionLocal()
    source = _make_completed_run(db)
    recently = datetime.now(timezone.utc) - timedelta(minutes=5)
    schedule = RecurringSchedule(
        name="daily", module_key=source.module_key, source_run_id=source.id,
        interval_minutes=1440, enabled=True, last_fired_at=recently,
    )
    db.add(schedule)
    db.commit()
    schedule_id = schedule.id
    db.close()

    check_recurring_schedules()

    assert enqueued == []
    db = SessionLocal()
    refreshed = db.get(RecurringSchedule, schedule_id)
    assert refreshed.last_run_id is None  # never fired - schedule wasn't due yet
    db.close()


def test_disabled_schedule_never_fires(monkeypatch):
    enqueued: list[str] = []
    monkeypatch.setattr(
        "app.workers.beat.get_job_runner",
        lambda: type("FakeRunner", (), {"enqueue": staticmethod(lambda run_id: enqueued.append(str(run_id)))})(),
    )

    db = SessionLocal()
    source = _make_completed_run(db)
    schedule = RecurringSchedule(
        name="disabled", module_key=source.module_key, source_run_id=source.id,
        interval_minutes=60, enabled=False, last_fired_at=None,
    )
    db.add(schedule)
    db.commit()
    db.close()

    check_recurring_schedules()
    assert enqueued == []


def test_schedule_with_incomplete_source_run_is_skipped(monkeypatch):
    enqueued: list[str] = []
    monkeypatch.setattr(
        "app.workers.beat.get_job_runner",
        lambda: type("FakeRunner", (), {"enqueue": staticmethod(lambda run_id: enqueued.append(str(run_id)))})(),
    )

    db = SessionLocal()
    source = Run(module_key="fake_test_module", status="failed", options={})
    db.add(source)
    db.commit()
    schedule = RecurringSchedule(
        name="broken-source", module_key=source.module_key, source_run_id=source.id,
        interval_minutes=60, enabled=True, last_fired_at=None,
    )
    db.add(schedule)
    db.commit()
    schedule_id = schedule.id
    db.close()

    check_recurring_schedules()

    assert enqueued == []
    db = SessionLocal()
    refreshed = db.get(RecurringSchedule, schedule_id)
    assert refreshed.last_fired_at is None  # never fired - source run was never completed
    db.close()
