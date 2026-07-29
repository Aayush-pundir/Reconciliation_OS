"""Job execution abstraction.

Two implementations selected by Settings.job_runner:
  - InProcessJobRunner: a background thread pool, zero extra infra. Default
    for local dev / `docker compose up` demos.
  - CeleryJobRunner: enqueues onto Redis for a horizontally-scalable worker
    pool. Production default (see ARCHITECTURE.md §4.2, §Deployment Topology).

Callers (the API layer) only ever call `enqueue(run_id)` - which concrete
runner executes it is a config switch, not an API-layer decision.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol
from uuid import UUID

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class JobRunner(Protocol):
    def enqueue(self, run_id: UUID) -> None: ...


class InProcessJobRunner:
    """Runs recon jobs on a local thread pool inside the API process.

    Not horizontally scalable (by design - it's the zero-infra dev path),
    but uses the exact same `execute_run` entrypoint as CeleryJobRunner so
    module behavior is identical regardless of runner.
    """

    def __init__(self, max_workers: int = 4) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="recon-job")

    def enqueue(self, run_id: UUID) -> None:
        self._pool.submit(self._run, run_id)

    @staticmethod
    def _run(run_id: UUID) -> None:
        from app.recon.engine import execute_run  # local import: avoid import cycles

        try:
            execute_run(str(run_id))
        except Exception:  # pragma: no cover - defensive; execute_run already handles/logs
            logger.exception("Unhandled error running job %s", run_id)


class CeleryJobRunner:
    def enqueue(self, run_id: UUID) -> None:
        from app.workers.tasks import run_reconciliation_task  # local import: avoid import cycles

        run_reconciliation_task.delay(str(run_id))


_runner_instance: JobRunner | None = None


def get_job_runner() -> JobRunner:
    global _runner_instance
    if _runner_instance is not None:
        return _runner_instance

    settings = get_settings()
    _runner_instance = CeleryJobRunner() if settings.job_runner == "celery" else InProcessJobRunner()
    return _runner_instance
