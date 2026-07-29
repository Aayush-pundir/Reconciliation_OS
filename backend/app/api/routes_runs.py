"""Run lifecycle API: create (upload+enqueue), list, detail, results,
report download, rerun, legacy import, exception annotation. See
ARCHITECTURE.md §6 for the full contract.

Live status updates use short client-side polling on `GET /runs/{id}`
rather than a websocket/SSE stream for v1 - simpler to operate, and the
2-second update-latency NFR is comfortably met by a 1.5s poll interval.
A push-based stream is a straightforward fast-follow (the Run/RunEvent
model already carries everything an SSE handler would need).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.job_runner import get_job_runner
from app.core.storage import get_storage
from app.models import Run, RunArtifact, RunEvent, RunFile, RunResult, User
from app.recon.importer import import_report as parse_legacy_report
from app.recon.module_config import get_effective_options
from app.recon.registry import get_module
from app.schemas.schemas import (
    AnnotateResultRequest,
    RunDetailOut,
    RunEventOut,
    RunFileOut,
    RunListPage,
    RunOut,
    RunResultOut,
    RunResultPage,
)

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _owned_run(db: Session, run_id: str, user: User) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    if user.role != "admin" and run.triggered_by != user.id:
        raise HTTPException(403, "Not authorized to view this run")
    return run


@router.post("", response_model=RunOut, status_code=201)
async def create_run(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> RunOut:
    form = await request.form()
    module_key = form.get("module_key")
    if not module_key:
        raise HTTPException(400, "module_key is required")
    module = get_module(str(module_key))
    if module is None:
        raise HTTPException(404, f"Unknown module '{module_key}'")

    try:
        options_override = json.loads(str(form.get("options") or "{}"))
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "options must be valid JSON") from exc

    # Admin-configured org-level defaults (routes_admin.py) are the base;
    # whatever this specific run passes overrides them.
    options = get_effective_options(db, str(module_key), options_override)

    run = Run(module_key=str(module_key), status="created", triggered_by=user.id, options=options)
    db.add(run)
    db.commit()

    storage = get_storage()
    slot_keys = {s.key for s in module.input_slots}
    for key in form.keys():
        if key not in slot_keys:
            continue
        for value in form.getlist(key):
            if not isinstance(value, StarletteUploadFile):
                continue
            content = await value.read()
            digest = hashlib.sha256(content).hexdigest()
            storage_path = f"runs/{run.id}/{key}/{value.filename}"
            storage.save(storage_path, content)
            db.add(
                RunFile(
                    run_id=run.id, slot=key, original_filename=value.filename or "unnamed",
                    content_hash=digest, size_bytes=len(content), storage_path=storage_path, validation_ok=True,
                )
            )
    db.commit()

    provided_slots = {f.slot for f in db.query(RunFile).filter(RunFile.run_id == run.id).all()}
    missing = [s.label for s in module.input_slots if s.required and s.key not in provided_slots]
    if missing:
        run.status = "failed"
        run.error_message = f"Missing required input(s): {', '.join(missing)}"
        db.add(run)
        db.commit()
        db.refresh(run)
        return RunOut.model_validate(run)

    run.status = "queued"
    db.add(run)
    db.commit()
    get_job_runner().enqueue(run.id)
    db.refresh(run)
    return RunOut.model_validate(run)


@router.post("/import", response_model=RunOut, status_code=201)
async def import_legacy_report(
    request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> RunOut:
    """Reconstructs a completed Run from a previously-exported report
    (Recon OS's own export, or one of the original tools' exports - both
    follow the same header-row-then-data-rows convention). Does not
    re-run any module's parse/reconcile logic; it archives the report's
    own numbers as-is, for run-history parity with pre-migration exports."""
    form = await request.form()
    module_key = str(form.get("module_key") or "")
    module = get_module(module_key) if module_key else None
    if module is None:
        raise HTTPException(400, "A valid module_key is required")

    file_value = form.get("file")
    if not isinstance(file_value, StarletteUploadFile):
        raise HTTPException(400, "file is required")
    content = await file_value.read()

    sheets = parse_legacy_report(content)
    if not sheets:
        raise HTTPException(400, "No readable sheets (with a header row) found in the uploaded workbook")

    now = datetime.now(timezone.utc)
    run = Run(
        module_key=module_key, status="completed", triggered_by=user.id,
        options={"imported": True}, started_at=now, completed_at=now,
    )
    db.add(run)
    db.commit()

    storage = get_storage()
    digest = hashlib.sha256(content).hexdigest()
    storage_path = f"runs/{run.id}/imported/{file_value.filename}"
    storage.save(storage_path, content)
    db.add(
        RunFile(
            run_id=run.id, slot="imported", original_filename=file_value.filename or "import.xlsx",
            content_hash=digest, size_bytes=len(content), storage_path=storage_path, validation_ok=True,
            validation_note="Imported from a previously-exported report",
        )
    )
    db.add(RunArtifact(run_id=run.id, kind="excel_report", storage_path=storage_path))

    for sheet in sheets:
        db.add(
            RunResult(
                run_id=run.id, kind=sheet["kind"], sheet_name=sheet["name"], row_index=-1,
                payload={"__meta__": True, "columns": sheet["columns"]},
            )
        )
        for i, row in enumerate(sheet["rows"]):
            db.add(RunResult(run_id=run.id, kind=sheet["kind"], sheet_name=sheet["name"], row_index=i, payload=row))

    db.add(RunEvent(run_id=run.id, from_status="created", to_status="completed", message="Imported from a legacy Excel export"))
    db.commit()
    db.refresh(run)
    return RunOut.model_validate(run)


@router.get("", response_model=RunListPage)
def list_runs(
    module_key: str | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RunListPage:
    query = db.query(Run)
    if user.role != "admin":
        query = query.filter(Run.triggered_by == user.id)
    if module_key:
        query = query.filter(Run.module_key == module_key)
    if status:
        query = query.filter(Run.status == status)
    if q:
        query = query.filter(Run.module_key.ilike(f"%{q}%"))
    total = query.count()
    items = query.order_by(Run.created_at.desc()).offset(offset).limit(limit).all()
    return RunListPage(total=total, items=[RunOut.model_validate(r) for r in items])


@router.get("/{run_id}", response_model=RunDetailOut)
def get_run(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> RunDetailOut:
    run = _owned_run(db, run_id, user)
    has_report = (
        db.query(RunArtifact).filter(RunArtifact.run_id == run_id, RunArtifact.kind == "excel_report").count() > 0
    )
    out = RunDetailOut.model_validate(run)
    out.files = [RunFileOut.model_validate(f) for f in run.files]
    out.events = [RunEventOut.model_validate(e) for e in run.events]
    out.has_report = has_report
    return out


@router.get("/{run_id}/results", response_model=RunResultPage)
def get_results(
    run_id: str,
    kind: str | None = None,
    sheet_name: str | None = None,
    limit: int = 500,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RunResultPage:
    _owned_run(db, run_id, user)

    query = db.query(RunResult).filter(RunResult.run_id == run_id, RunResult.row_index >= 0)
    if kind:
        query = query.filter(RunResult.kind == kind)
    if sheet_name:
        query = query.filter(RunResult.sheet_name == sheet_name)
    total = query.count()
    items = query.order_by(RunResult.sheet_name, RunResult.row_index).offset(offset).limit(limit).all()

    sheet_names = {i.sheet_name for i in items}
    columns_by_sheet: dict[str, list[str] | None] = {}
    for sheet in sheet_names:
        meta = (
            db.query(RunResult)
            .filter(RunResult.run_id == run_id, RunResult.sheet_name == sheet, RunResult.row_index == -1)
            .first()
        )
        columns_by_sheet[sheet] = meta.payload.get("columns") if meta else None

    return RunResultPage(
        total=total,
        items=[
            RunResultOut(
                id=i.id, kind=i.kind, sheet_name=i.sheet_name, columns=columns_by_sheet.get(i.sheet_name),
                row_index=i.row_index, payload=i.payload, annotation_status=i.annotation_status,
                annotation_note=i.annotation_note, annotation_at=i.annotation_at,
            )
            for i in items
        ],
    )


@router.patch("/{run_id}/results/{result_id}/annotate", response_model=RunResultOut)
def annotate_result(
    run_id: str,
    result_id: str,
    payload: AnnotateResultRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RunResultOut:
    """Bulk exception actions: acknowledge/resolve/note an exception row
    without leaving the results table."""
    _owned_run(db, run_id, user)
    result = db.get(RunResult, result_id)
    if result is None or result.run_id != run_id:
        raise HTTPException(404, "Result row not found")

    result.annotation_status = payload.status or None
    result.annotation_note = payload.note
    result.annotation_by = user.id
    result.annotation_at = datetime.now(timezone.utc)
    db.add(result)
    db.commit()
    db.refresh(result)
    return RunResultOut(
        id=result.id, kind=result.kind, sheet_name=result.sheet_name, columns=None, row_index=result.row_index,
        payload=result.payload, annotation_status=result.annotation_status, annotation_note=result.annotation_note,
        annotation_at=result.annotation_at,
    )


@router.get("/{run_id}/sheets", response_model=list[str])
def list_sheets(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[str]:
    _owned_run(db, run_id, user)
    rows = db.query(RunResult.sheet_name).filter(RunResult.run_id == run_id, RunResult.row_index == -1).all()
    return [r[0] for r in rows]


@router.get("/{run_id}/report")
def download_report(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    run = _owned_run(db, run_id, user)
    artifact = (
        db.query(RunArtifact)
        .filter(RunArtifact.run_id == run_id, RunArtifact.kind == "excel_report")
        .order_by(RunArtifact.generated_at.desc())
        .first()
    )
    if artifact is None:
        raise HTTPException(404, "Report not available yet")
    data = get_storage().open(artifact.storage_path)
    filename = f"{run.module_key}_{run.id[:8]}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{run_id}/rerun", response_model=RunOut, status_code=201)
def rerun(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> RunOut:
    """Re-queues a past run's exact input file set without re-uploading (PRD F4)."""
    old_run = _owned_run(db, run_id, user)
    new_run = Run(module_key=old_run.module_key, status="queued", triggered_by=user.id, options=old_run.options)
    db.add(new_run)
    db.commit()

    for f in db.query(RunFile).filter(RunFile.run_id == old_run.id).all():
        db.add(
            RunFile(
                run_id=new_run.id, slot=f.slot, original_filename=f.original_filename, content_hash=f.content_hash,
                size_bytes=f.size_bytes, storage_path=f.storage_path, validation_ok=f.validation_ok,
            )
        )
    db.commit()

    get_job_runner().enqueue(new_run.id)
    db.refresh(new_run)
    return RunOut.model_validate(new_run)
