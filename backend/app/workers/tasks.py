from __future__ import annotations

from app.recon.engine import execute_run
from app.workers.celery_app import celery_app


@celery_app.task(name="recon_os.run_reconciliation", bind=True, max_retries=0)
def run_reconciliation_task(self, run_id: str) -> None:
    """Identical execution path to InProcessJobRunner - see
    `app.recon.engine.execute_run` for the parse->validate->reconcile->
    report pipeline every module goes through."""
    execute_run(run_id)
