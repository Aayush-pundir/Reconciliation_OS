"""Run lifecycle API: create (upload+enqueue), list, detail, results,
report download, rerun. See ARCHITECTURE.md §6 for the full contract.

Live status updates use short client-side polling on `GET /runs/{id}`
rather than a websocket/SSE stream for v1 - simpler to operate, and the
2-second update-latency NFR is comfortably met by a 1.5s poll interval.
A push-based stream is a straightforward fast-follow (the Run/RunEvent
model already carries everything an SSE handler would need).
"""
from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.job_runner import get_job_runner
from app.core.storage import get_storage
from app.models import Run, RunArtifact, RunFile, RunResult, User
from app.recon.registry import get_module
from app.schemas.schemas import RunDetailOut, RunEventOut, RunFileOut, RunListPage, RunOut, RunResultOut, RunResultPage

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
        options = json.loads(str(form.get("options") or "{}"))
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "options must be valid JSON") from exc

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
                kind=i.kind, sheet_name=i.sheet_name, columns=columns_by_sheet.get(i.sheet_name),
                row_index=i.row_index, payload=i.payload,
            )
            for i in items
        ],
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
