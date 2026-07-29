"""Scheduled recurring runs - periodically re-fires a saved run's exact
input files (rerun mechanics) on an interval, via a Celery-beat poller
(app/workers/beat.py::check_recurring_schedules).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import RecurringSchedule, Run, User
from app.schemas.schemas import RecurringScheduleCreateRequest, RecurringScheduleOut, RecurringScheduleUpdateRequest

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


@router.post("", response_model=RecurringScheduleOut, status_code=201)
def create_schedule(
    payload: RecurringScheduleCreateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> RecurringScheduleOut:
    source = db.get(Run, payload.source_run_id)
    if source is None:
        raise HTTPException(404, "Source run not found")
    if source.status != "completed":
        raise HTTPException(400, "Source run must be completed before it can be scheduled")

    schedule = RecurringSchedule(
        name=payload.name,
        module_key=source.module_key,
        source_run_id=source.id,
        interval_minutes=payload.interval_minutes,
        enabled=True,
        created_by=user.id,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return RecurringScheduleOut.model_validate(schedule)


@router.get("", response_model=list[RecurringScheduleOut])
def list_schedules(db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> list[RecurringScheduleOut]:
    schedules = db.query(RecurringSchedule).order_by(RecurringSchedule.created_at.desc()).all()
    return [RecurringScheduleOut.model_validate(s) for s in schedules]


@router.patch("/{schedule_id}", response_model=RecurringScheduleOut)
def update_schedule(
    schedule_id: str,
    payload: RecurringScheduleUpdateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> RecurringScheduleOut:
    schedule = db.get(RecurringSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(404, "Schedule not found")
    if payload.enabled is not None:
        schedule.enabled = payload.enabled
    if payload.interval_minutes is not None:
        schedule.interval_minutes = payload.interval_minutes
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return RecurringScheduleOut.model_validate(schedule)


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> None:
    schedule = db.get(RecurringSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(404, "Schedule not found")
    db.delete(schedule)
    db.commit()
