# Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
Dates reflect when the work happened, not a formal release process.

## Unreleased — fast-follow batch (2026-07-29)

Follow-up to the v1.0.0 platform build, addressing direct product feedback:
regressions from the port (folder upload, no new features), UI/UX gaps, and
the mandatory login requirement — plus the remaining backend scaffolding
(admin config, API keys, scheduling, notifications) built out to real,
working features with UI.

### Added
- **Optional auth.** `AUTH_REQUIRED` defaults to `false` — no login screen;
  every request resolves to a shared local user. JWT login and X-API-Key
  auth still work when explicitly turned on (e.g. shared/exposed infra).
- **Folder upload.** A "select a whole folder" picker (`webkitdirectory`)
  and recursive drag-and-drop folder traversal (`FileSystemEntry` API),
  restoring a capability the original NFS/UPI/FASTag/RuPay tools had that
  was lost in the initial port. Folder-sourced files are filtered against
  each input slot's accepted extensions.
- **Legacy report re-import.** `POST /api/runs/import` + a matching UI on
  each module's Run page: pick a previously-exported Excel report (Recon
  OS's own, or the original tool's) and archive it as a completed run
  without re-parsing/re-reconciling.
- **Bulk exception actions.** Acknowledge/resolve/note any exception row
  inline in the results table, persisted via
  `PATCH /api/runs/{id}/results/{id}/annotate`.
- **UI/UX pass.** Toast notifications for run start/failure, import,
  re-run, and annotation outcomes; loading skeletons replacing bare
  "Loading…" text; CSV export from any result table; a hand-rolled SVG
  trend chart on the Dashboard (completed/failed/in-progress run volume,
  last 14 days) — no new frontend dependencies added.
- **Admin — module defaults.** `/admin` page (admin-only) for setting
  org-level default options per module, merged under a run's own options
  at creation time.
- **API keys.** Create/list/revoke service-to-service API keys from
  `/admin`; the raw key is shown once at creation, only its prefix persists
  after that.
- **Scheduled recurring runs.** A "🔁 Schedule" button on any completed
  run's detail page creates a `RecurringSchedule` (hourly/daily/weekly);
  a Celery-beat task (`app/workers/beat.py`, polled every 60s) fires due
  schedules by cloning the source run's exact input files into a new run.
  Managed (pause/resume/delete) from `/admin`.
- **Notifications.** `app/core/notify.py` sends a best-effort email
  and/or Slack notification on every run completion/failure, selected via
  `NOTIFY_BACKEND` (`none` default | `email` | `slack` | `both`).

### Fixed
- **Stat-card / summary-sheet kind collision.** The engine persisted
  StatCard rows under `kind="summary"`, colliding with NFS's and UPI's own
  `kind="summary"` data sheets (Daily Summary, Pivot). The dashboard's
  stat-card row was silently rendering those tabular rows as garbage stat
  cards for every NFS/UPI run. StatCard rows now use a reserved
  `kind="stats"`, decoupled from any module's own sheet kinds.
- **Beat scheduler timezone bug.** `check_recurring_schedules` crashed
  comparing a tz-aware "now" against `last_fired_at` on SQLite, which
  (unlike Postgres) doesn't preserve `tzinfo` on `DateTime(timezone=True)`
  read-back — values come back naive. Now normalizes naive timestamps to
  UTC before comparing.

### Testing
- NFS merged-workbook and multi-block parsing coverage (same-date/
  cross-date cycle sequences, HTML-vs-`.xlsx` cycle-assignment asymmetry,
  dropped-incomplete-block handling, carry-over bank entries, direct
  `extract_date`/`cycle_from_filename` unit coverage).
- Load test (`backend/scripts/load_test.py`): 500 synthetic UPI NTSL files
  and 150 RuPay DSR files, end to end in 2.3s / 0.6s respectively, 100%
  match rate, 0 error-level findings.
- Backend test suite grew from 33 to 61 tests across this batch.

## v1.0.0 — initial platform (2026-07-28)

Consolidated 7 standalone reconciliation tools (5 HTML/JS utilities for
NFS/RuPay/UPI/FASTag/PG-recon, one VBA macro + workbook for Bank vs Add
Money, one Streamlit script for 6F/6R data prep) into one full-stack
platform: FastAPI + SQLAlchemy backend, React + TypeScript frontend,
Celery/Redis job queue with a zero-infra in-process fallback, Docker
Compose orchestration. See `docs/PRD.md` and `docs/ARCHITECTURE.md` for
the full spec this build was scoped against.

- Plugin architecture (`ReconModule` ABC) driving a single generic
  parse → validate → reconcile → build_report engine for all 7 modules.
- Every module's business logic ported line-for-line from its source
  (JS/VBA/Python), including several deliberately-preserved quirks — see
  `docs/KNOWN_DEVIATIONS.md`.
- One bug found and fixed during the port, ahead of the Python port:
  the Bank vs Add Money VBA macro's error-path cleanup, `IIf()`
  eager-evaluation crash, and a wrong/unused color constant.
- 33 backend unit tests (one per module plus the engine contract test),
  Docker Compose stack, JWT auth + seeded admin login.
