"""Pydantic request/response schemas for the API layer (ARCHITECTURE.md §6)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str
    role: str


class ModuleSchemaOut(BaseModel):
    key: str
    display_name: str
    description: str
    version: str
    input_slots: list[dict[str, Any]]
    options_schema: dict[str, Any]


class RunFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    slot: str
    original_filename: str
    size_bytes: int
    validation_ok: bool
    validation_note: str | None = None


class RunEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    from_status: str
    to_status: str
    message: str | None = None
    created_at: datetime


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    module_key: str
    module_version: str
    status: str
    triggered_by: str | None = None
    options: dict[str, Any]
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class RunDetailOut(RunOut):
    files: list[RunFileOut] = []
    events: list[RunEventOut] = []
    has_report: bool = False


class RunResultOut(BaseModel):
    id: str | None = None
    kind: str
    sheet_name: str
    columns: list[str] | None = None
    row_index: int
    payload: dict[str, Any]
    annotation_status: str | None = None
    annotation_note: str | None = None
    annotation_at: datetime | None = None


class RunResultPage(BaseModel):
    total: int
    items: list[RunResultOut]


class RunListPage(BaseModel):
    total: int
    items: list[RunOut]


class AnnotateResultRequest(BaseModel):
    status: str  # "acknowledged" | "resolved" | "" (clear)
    note: str | None = None


class ApiKeyCreateRequest(BaseModel):
    name: str


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    key_prefix: str
    created_at: datetime
    revoked_at: datetime | None = None


class ApiKeyCreatedOut(BaseModel):
    id: str
    name: str
    key_prefix: str
    created_at: datetime
    api_key: str  # only ever returned once, at creation time


class ModuleConfigOut(BaseModel):
    module_key: str
    default_options: dict[str, Any]
    updated_at: datetime | None = None


class ModuleConfigUpdateRequest(BaseModel):
    default_options: dict[str, Any]


class RecurringScheduleCreateRequest(BaseModel):
    name: str
    source_run_id: str
    interval_minutes: int = 1440


class RecurringScheduleUpdateRequest(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = None


class RecurringScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    module_key: str
    source_run_id: str
    interval_minutes: int
    enabled: bool
    last_fired_at: datetime | None = None
    last_run_id: str | None = None
    created_at: datetime
