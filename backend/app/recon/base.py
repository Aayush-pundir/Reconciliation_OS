"""Core recon-module contract. Every reconciliation type (NFS, RuPay, UPI,
FASTag, PG Recon, Bank-vs-AddMoney, 6F, and any future module) implements
`ReconModule`. See ARCHITECTURE.md §4.1.

Design intent: `parse()`/`reconcile()` return module-owned data shapes (via
the opaque `ParsedData.data` / `ReconOutput.raw` escape hatches) so each
module's internal representation can be as rich as it needs (mirroring the
original tool's own internal objects) - while `ReconOutput.stats`/`sheets`/
`findings` are the *generic* projection the engine persists and the
frontend renders identically for every module, without per-module UI code.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FindingLevel = Literal["ok", "warn", "err"]
SheetKind = Literal["summary", "detail", "exception", "validation"]
StatTone = Literal["neutral", "good", "bad", "warn"]


class InputSlot(BaseModel):
    """One upload target a module needs (e.g. NFS needs an 'ntsl' slot and
    a 'bank' slot). Drives the dynamic upload UI (PRD §10, screen 2)."""

    key: str
    label: str
    accept: list[str]
    multiple: bool = False
    required: bool = True
    filename_pattern: str | None = None
    help_text: str | None = None


class UploadedFile(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    slot: str
    filename: str
    content: bytes
    size_bytes: int


class RunContext(BaseModel):
    """Everything a module needs to do its job for one run, plus a
    lightweight structured log the module can append to (surfaced to the
    UI the same way the original tools' `<div class="logbox">` panels
    worked)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str
    options: dict[str, Any] = Field(default_factory=dict)
    files: list[UploadedFile] = Field(default_factory=list)
    log: list[str] = Field(default_factory=list)

    def files_for(self, slot: str) -> list[UploadedFile]:
        return [f for f in self.files if f.slot == slot]

    def info(self, msg: str) -> None:
        self.log.append(f"[INFO] {msg}")

    def ok(self, msg: str) -> None:
        self.log.append(f"[OK] {msg}")

    def warn(self, msg: str) -> None:
        self.log.append(f"[WARN] {msg}")

    def error(self, msg: str) -> None:
        self.log.append(f"[ERR] {msg}")


class ValidationFinding(BaseModel):
    """One line item within a named validation pass - e.g. RuPay's V1/V2/V3
    or UPI's Pass 1/2/3 checks (PRD F7: each check is surfaced discretely,
    never collapsed into a single boolean)."""

    pass_name: str
    check: str
    level: FindingLevel
    message: str


class StatCard(BaseModel):
    label: str
    value: str
    tone: StatTone = "neutral"
    sub: str | None = None


class ReportSheet(BaseModel):
    """One named, tabular result section - becomes one frontend tab, one
    family of persisted RunResult rows, and (via each module's own
    build_report) informs one Excel worksheet."""

    name: str
    kind: SheetKind
    columns: list[str]
    rows: list[dict[str, Any]]


class ParsedData(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    data: Any = None


class ReconOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    stats: list[StatCard] = Field(default_factory=list)
    sheets: list[ReportSheet] = Field(default_factory=list)
    findings: list[ValidationFinding] = Field(default_factory=list)
    raw: Any = None  # module-owned rich intermediate data for build_report() to consume


class OptionsBase(BaseModel):
    """Base class every module's options schema extends (e.g. match tolerance,
    month filter). Serialized via `.model_json_schema()` to drive the
    frontend's run-options form generically."""


class ReconModule(ABC):
    key: str
    display_name: str
    description: str = ""
    version: str = "1.0.0"
    input_slots: list[InputSlot] = []
    options_schema: type[OptionsBase] = OptionsBase

    @abstractmethod
    def parse(self, ctx: RunContext) -> ParsedData: ...

    @abstractmethod
    def validate(self, parsed: ParsedData, ctx: RunContext) -> list[ValidationFinding]: ...

    @abstractmethod
    def reconcile(
        self, parsed: ParsedData, ctx: RunContext, findings: list[ValidationFinding]
    ) -> ReconOutput: ...

    @abstractmethod
    def build_report(self, output: ReconOutput, ctx: RunContext) -> bytes: ...

    def schema(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
            "input_slots": [s.model_dump() for s in self.input_slots],
            "options_schema": self.options_schema.model_json_schema(),
        }
