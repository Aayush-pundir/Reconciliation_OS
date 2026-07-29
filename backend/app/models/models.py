"""SQLAlchemy ORM models - see ARCHITECTURE.md §5 Data Model for the ER diagram."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="analyst")  # "analyst" | "admin"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    runs: Mapped[list["Run"]] = relationship(back_populates="triggered_by_user")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    module_key: Mapped[str] = mapped_column(String(64), index=True)
    module_version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    # created -> uploaded -> queued -> parsing -> validating -> matching -> reporting -> completed | failed
    triggered_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    triggered_by_user: Mapped[User | None] = relationship(back_populates="runs")
    files: Mapped[list["RunFile"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    results: Mapped[list["RunResult"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    events: Mapped[list["RunEvent"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="RunEvent.created_at"
    )
    artifacts: Mapped[list["RunArtifact"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class RunFile(Base):
    __tablename__ = "run_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), index=True)
    slot: Mapped[str] = mapped_column(String(64))
    original_filename: Mapped[str] = mapped_column(String(512))
    content_hash: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    storage_path: Mapped[str] = mapped_column(String(1024))
    validation_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    validation_note: Mapped[str | None] = mapped_column(String(512), nullable=True)

    run: Mapped[Run] = relationship(back_populates="files")


class RunResult(Base):
    __tablename__ = "run_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # summary | detail | exception | validation
    sheet_name: Mapped[str] = mapped_column(String(128))
    row_index: Mapped[int] = mapped_column(default=0)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    # Bulk exception actions (PRD fast-follow): analysts can acknowledge/note
    # an exception row without needing a separate join table, since each
    # RunResult row already *is* one exception line item.
    annotation_status: Mapped[str | None] = mapped_column(String(32), nullable=True)  # acknowledged | resolved
    annotation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    annotation_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    annotation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[Run] = relationship(back_populates="results")


class RunEvent(Base):
    __tablename__ = "run_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), index=True)
    from_status: Mapped[str] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped[Run] = relationship(back_populates="events")


class RunArtifact(Base):
    __tablename__ = "run_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="excel_report")
    storage_path: Mapped[str] = mapped_column(String(1024))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped[Run] = relationship(back_populates="artifacts")


class ApiKey(Base):
    """Service-to-service credential, separate from human login (which is
    optional/off by default). Callers send the raw key once at creation
    time; only its salted hash is ever persisted."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    key_prefix: Mapped[str] = mapped_column(String(12))  # shown in UI so the key is identifiable post-creation
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModuleConfig(Base):
    """Org-level default options per module (admin-configurable), used as
    the base a run's own options are layered on top of."""

    __tablename__ = "module_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    module_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    default_options: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    updated_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)


class RecurringSchedule(Base):
    """Periodically re-runs a saved run's exact input file set (rerun
    mechanics, on a timer) - a Celery-beat task polls for due schedules.
    See app/workers/beat.py."""

    __tablename__ = "recurring_schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    module_key: Mapped[str] = mapped_column(String(64), index=True)
    source_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"))
    interval_minutes: Mapped[int] = mapped_column(default=1440)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("runs.id"), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
