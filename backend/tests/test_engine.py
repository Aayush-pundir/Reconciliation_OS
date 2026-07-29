"""Contract test: the engine persists Run status transitions, findings,
and sheet rows identically for any module - independent of that module's
own logic (ARCHITECTURE.md §9)."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.core.database import Base, SessionLocal, engine
from app.models import Run, RunEvent, RunResult
from app.recon.base import (
    InputSlot,
    OptionsBase,
    ParsedData,
    ReconModule,
    ReconOutput,
    ReportSheet,
    RunContext,
    StatCard,
    ValidationFinding,
)
from app.recon.engine import execute_run
from app.recon.registry import register


class _FakeModule(ReconModule):
    key = "fake_test_module"
    display_name = "Fake"
    version = "9.9.9"
    input_slots = [InputSlot(key="f", label="F", accept=[".txt"], required=False)]
    options_schema = OptionsBase

    def parse(self, ctx: RunContext) -> ParsedData:
        return ParsedData(data={"ok": True})

    def validate(self, parsed, ctx):
        return [ValidationFinding(pass_name="P1", check="c1", level="ok", message="fine")]

    def reconcile(self, parsed, ctx, findings):
        return ReconOutput(
            stats=[StatCard(label="Total", value="1")],
            sheets=[ReportSheet(name="Detail", kind="detail", columns=["a", "b"], rows=[{"a": 1, "b": 2}])],
            findings=[],
        )

    def build_report(self, output, ctx):
        return b"fake-bytes"


register(_FakeModule())


def setup_module() -> None:
    Base.metadata.create_all(bind=engine)


def test_execute_run_transitions_and_persists_results(tmp_path, monkeypatch):
    from app.core import storage as storage_mod

    monkeypatch.setattr(storage_mod, "_storage_instance", storage_mod.LocalFsStorage(str(tmp_path)))

    db = SessionLocal()
    run = Run(module_key="fake_test_module", status="created")
    db.add(run)
    db.commit()
    run_id = run.id
    db.close()

    execute_run(run_id)

    db = SessionLocal()
    completed = db.get(Run, run_id)
    assert completed.status == "completed"
    assert completed.module_version == "9.9.9"

    events = db.query(RunEvent).filter(RunEvent.run_id == run_id).all()
    statuses = [e.to_status for e in events]
    assert statuses == ["parsing", "validating", "matching", "reporting", "completed"]

    results = db.query(RunResult).filter(RunResult.run_id == run_id).all()
    kinds = {r.kind for r in results}
    assert "summary" in kinds
    assert "detail" in kinds
    assert "validation" in kinds
    db.close()
