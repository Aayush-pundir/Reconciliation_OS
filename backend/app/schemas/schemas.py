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
    kind: str
    sheet_name: str
    columns: list[str] | None = None
    row_index: int
    payload: dict[str, Any]


class RunResultPage(BaseModel):
    total: int
    items: list[RunResultOut]


class RunListPage(BaseModel):
    total: int
    items: list[RunOut]
