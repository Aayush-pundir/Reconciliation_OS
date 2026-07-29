"""Drives any registered ReconModule through parse -> validate -> reconcile
-> build_report, persisting Run status transitions (audit trail, PRD F9),
structured results (PRD F5), and the generated Excel artifact - identically
for every module. This is the entire point of the plugin architecture:
this file has zero module-specific logic.
"""
from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.notify import get_notifier
from app.core.storage import get_storage
from app.models import Run, RunArtifact, RunEvent, RunFile, RunResult
from app.recon.base import ReconOutput, RunContext, UploadedFile, ValidationFinding
from app.recon.registry import get_module

logger = logging.getLogger(__name__)


def _transition(db: Session, run: Run, to_status: str, message: str | None = None) -> None:
    from_status = run.status
    run.status = to_status
    if to_status == "parsing" and run.started_at is None:
        run.started_at = datetime.now(timezone.utc)
    if to_status in ("completed", "failed"):
        run.completed_at = datetime.now(timezone.utc)
    db.add(RunEvent(run_id=run.id, from_status=from_status, to_status=to_status, message=message))
    db.add(run)
    db.commit()


def _persist_findings(db: Session, run_id: str, findings: list[ValidationFinding]) -> None:
    for i, finding in enumerate(findings):
        db.add(
            RunResult(
                run_id=run_id,
                kind="validation",
                sheet_name=finding.pass_name,
                row_index=i,
                payload=finding.model_dump(),
            )
        )
    db.commit()


def _notify(run: Run, status: str, detail: str = "") -> None:
    """Best-effort: a notification failure (bad SMTP creds, Slack webhook
    down, etc.) must never fail the run itself."""
    try:
        subject = f"Recon OS: {run.module_key} run {status}"
        message = f"Run {run.id} ({run.module_key}) {status}."
        if detail:
            message += f"\n\n{detail}"
        get_notifier().notify(subject, message)
    except Exception:  # noqa: BLE001
        logger.exception("Notification failed for run %s (status=%s)", run.id, status)


def _persist_output(db: Session, run_id: str, output: ReconOutput) -> None:
    # "stats" is a reserved kind distinct from ReportSheet's "summary" kind:
    # several modules (NFS, UPI) use kind="summary" for real tabular sheets
    # (Daily Summary, Pivot) - sharing a kind with StatCard rows would mean
    # the dashboard's stat-card query pulls in those data rows too.
    for i, stat in enumerate(output.stats):
        db.add(
            RunResult(run_id=run_id, kind="stats", sheet_name="stats", row_index=i, payload=stat.model_dump())
        )
    for sheet in output.sheets:
        # row_index=-1 carries column order metadata for this sheet, once.
        db.add(
            RunResult(
                run_id=run_id,
                kind=sheet.kind,
                sheet_name=sheet.name,
                row_index=-1,
                payload={"__meta__": True, "columns": sheet.columns},
            )
        )
        for i, row in enumerate(sheet.rows):
            db.add(RunResult(run_id=run_id, kind=sheet.kind, sheet_name=sheet.name, row_index=i, payload=row))
    db.commit()


def execute_run(run_id: str) -> None:
    """Entrypoint called by both InProcessJobRunner and the Celery task -
    identical execution path regardless of which JobRunner triggered it.
    """
    db = SessionLocal()
    storage = get_storage()
    try:
        run = db.get(Run, run_id)
        if run is None:
            return

        module = get_module(run.module_key)
        if module is None:
            _transition(db, run, "failed", f"Unknown module '{run.module_key}'")
            _notify(run, "failed", f"Unknown module '{run.module_key}'")
            return

        run.module_version = module.version
        db.add(run)
        db.commit()

        run_files = db.query(RunFile).filter(RunFile.run_id == run.id).all()
        uploaded = [
            UploadedFile(
                slot=f.slot,
                filename=f.original_filename,
                content=storage.open(f.storage_path),
                size_bytes=f.size_bytes,
            )
            for f in run_files
        ]
        ctx = RunContext(run_id=run.id, options=run.options or {}, files=uploaded)

        _transition(db, run, "parsing")
        parsed = module.parse(ctx)

        _transition(db, run, "validating")
        findings = module.validate(parsed, ctx)
        _persist_findings(db, run.id, findings)

        _transition(db, run, "matching")
        output = module.reconcile(parsed, ctx, findings)
        _persist_findings(db, run.id, output.findings)
        _persist_output(db, run.id, output)

        _transition(db, run, "reporting")
        report_bytes = module.build_report(output, ctx)
        artifact_key = f"runs/{run.id}/report.xlsx"
        storage.save(artifact_key, report_bytes)
        db.add(RunArtifact(run_id=run.id, kind="excel_report", storage_path=artifact_key))
        db.commit()

        _transition(db, run, "completed")
        _notify(run, "completed")
    except Exception as exc:  # noqa: BLE001 - top-level job boundary; must never crash the worker
        db.rollback()
        run = db.get(Run, run_id)
        if run is not None:
            trace = traceback.format_exc()[-4000:]
            _transition(db, run, "failed", f"{exc}\n{trace}")
            _notify(run, "failed", str(exc))
    finally:
        db.close()
