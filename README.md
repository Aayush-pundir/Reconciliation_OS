# 🧮 Recon OS: Unified Reconciliation Platform

A full-stack internal platform that replaces seven independent, offline reconciliation tools (5 standalone HTML/JS utilities, 1 VBA macro + workbook, 1 Streamlit script) with a single upload → reconcile → review → export flow — persisted run history, structured queryable results, and an audit trail across every settlement network Eroute Technologies reconciles against.

**Status:** Production-ready core (all 7 modules ported + tested) · Fast-follow batch shipped (scheduling, notifications, admin tooling, UI/UX pass)

## 🌟 Project Vision

Every original tool solved one reconciliation problem well, in isolation: open a file, click a button, get an Excel export, repeat tomorrow. That meant no run history, no audit trail, a frozen browser tab on large batches, and a different UI muscle-memory per network. Recon OS keeps every tool's business logic byte-for-byte faithful — same fee formulas, same matching tolerances, same validation passes — while giving it:

- **One consistent UI** across NFS, RuPay, UPI, FASTag, PG Recon, Bank vs Add Money, and 6F/6R Data Prep
- **Async, server-side processing** — upload and walk away; no more browser tab freezing on a 500-file UPI batch
- **Persisted, queryable results** — every run's rows are in Postgres, not just a downloaded `.xlsx`
- **A plugin architecture** where an eighth reconciliation type is one new Python file + one registration line, no other code touched

## 📋 Current Implementation Status

### ✅ Implemented
- All 7 reconciliation modules, faithfully ported (see [`docs/KNOWN_DEVIATIONS.md`](docs/KNOWN_DEVIATIONS.md) for every place behavior deliberately differs from a literal copy, and why)
- Plugin engine (`ReconModule` ABC) driving one generic parse → validate → reconcile → build_report pipeline for every module
- Async job execution — Celery + Redis in production, a zero-infra in-process thread pool for local dev, same code path either way
- Folder upload (picker + recursive drag-and-drop) alongside individual multi-file upload
- Legacy Excel report re-import (archive a prior export as a completed run, no re-parsing)
- Bulk exception actions (acknowledge / resolve / note, inline in the results table)
- Optional auth — no login screen by default (shared local user); JWT login + API keys available behind a config flag for shared/exposed infra
- Admin console: org-level default options per module, API key management, recurring-schedule management
- Scheduled recurring runs (Celery-beat) — re-fire a saved run's exact input files on an hourly/daily/weekly cadence
- Email/Slack notifications on run completion/failure
- Toasts, loading skeletons, CSV export, a dashboard trend chart
- 61 backend tests (one regression suite per module + engine/beat/notifier contract tests); 500-file UPI and 150-file RuPay load tests (2.3s / 0.6s end to end, 100% match rate)

### 🔄 Known Gaps
- NFS, UPI, RuPay, and FASTag parsing has **not** been validated against real production NPCI/bank export files — only synthetic fixtures matching the documented format (PG Recon is validated against the real embedded sample from the original workbook). See [`docs/KNOWN_DEVIATIONS.md`](docs/KNOWN_DEVIATIONS.md).
- Live status updates use 1.5s client-side polling, not a websocket/SSE push — the `Run`/`RunEvent` data model already carries everything a push stream would need.

### 📅 Planned
- Dark mode
- Run-to-run comparison view
- Real-time push updates (SSE) in place of polling

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, TanStack Query + Table, React Router |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2 |
| Job Queue | Celery + Redis (production) · in-process thread pool (zero-infra local dev) — same `execute_run` entrypoint either way |
| Database | PostgreSQL 16 (production) · SQLite (zero-infra local dev) |
| Notifications | SMTP (email) / Slack incoming webhook, pluggable `Notifier` abstraction |
| Auth | JSON Web Tokens (python-jose), bcrypt (human passwords), SHA-256 (API keys) — all optional, off by default |
| Excel I/O | openpyxl (styled, formula-driven `.xlsx` reports), pandas, BeautifulSoup4/lxml (NPCI's mislabeled HTML-as-`.xls` exports) |
| Deployment | Docker Compose (postgres, redis, backend, worker, beat, frontend/nginx) |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Frontend (React + Vite)                      │
│   Dashboard · Module Run (upload) · Run Detail · Run History ·  │
│   Admin (module defaults / API keys / schedules)                │
└───────────────────────────┬───────────────────────────────────┘
                             │ REST (fetch), polled for live status
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Backend (FastAPI, port 8000)                   │
│  ├─ routes_auth      login / current-user resolution            │
│  ├─ routes_modules   module schema discovery (input slots, opts)│
│  ├─ routes_runs      create / list / detail / results / report /│
│  │                    rerun / legacy import / annotate          │
│  ├─ routes_admin     org-level module default options           │
│  ├─ routes_api_keys  service-to-service credential CRUD         │
│  └─ routes_schedules recurring-schedule CRUD                    │
└──────┬──────────────────────────┬────────────────────────┬─────┘
       │ enqueue(run_id)          │ SQLAlchemy               │ save/open
       ▼                          ▼                           ▼
┌─────────────┐         ┌──────────────────┐         ┌───────────────┐
│  Job Runner  │         │   PostgreSQL     │         │  File Storage  │
│ Celery worker│         │  Run/RunFile/    │         │ local fs / S3  │
│  (port 6379  │         │  RunResult/...   │         └───────────────┘
│   via Redis) │         └──────────────────┘
└──────┬───────┘
       │ execute_run(): parse → validate → reconcile → build_report
       ▼
┌─────────────────────────────────────────────────────────────────┐
│         Recon Engine — one of 7 registered ReconModules         │
│   nfs · rupay · upi · fastag · pg_recon · bank_addmoney ·        │
│   data_prep_6f                                                  │
└─────────────────────────────────────────────────────────────────┘

Celery-beat (separate single-instance process) polls every 60s for
due RecurringSchedules and re-queues them through the same job runner.
```

Full rationale for every architectural choice: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## 📊 Data Models

```
Run {
  id, module_key, module_version, status,        # created→queued→parsing→
  triggered_by (User), options (JSON),            # validating→matching→
  error_message, created_at,                      # reporting→completed|failed
  started_at, completed_at
}

RunFile {
  id, run_id, slot, original_filename,
  content_hash (sha256), size_bytes,
  storage_path, validation_ok, validation_note
}

RunResult {
  id, run_id, kind ("stats"|"detail"|"exception"|"validation"|"summary"),
  sheet_name, row_index (-1 = column-metadata row), payload (JSON),
  annotation_status, annotation_note, annotation_by, annotation_at
}

RunEvent { id, run_id, from_status, to_status, message, created_at }
RunArtifact { id, run_id, kind ("excel_report"), storage_path, generated_at }

User { id, email, name, password_hash, role ("analyst"|"admin"), created_at }
ApiKey { id, name, key_prefix, key_hash (sha256), user_id, created_at, revoked_at }
ModuleConfig { id, module_key (unique), default_options (JSON), updated_at, updated_by }
RecurringSchedule {
  id, name, module_key, source_run_id, interval_minutes, enabled,
  last_fired_at, last_run_id, created_by, created_at
}
```

## 🔌 API Endpoints

### Auth
- `POST /api/auth/login` — email/password login (only needed if `AUTH_REQUIRED=true`)
- `GET /api/auth/me` — resolve current identity (local user by default)

### Modules
- `GET /api/modules` — list all 7 registered modules with their input slots + options schema

### Runs
- `POST /api/runs` — create a run (multipart upload + module_key + options)
- `POST /api/runs/import` — archive a previously-exported report as a completed run
- `GET /api/runs` — list runs (filter by module_key / status / query, paginated)
- `GET /api/runs/{id}` — run detail (files, events, status)
- `GET /api/runs/{id}/results` — paginated result rows (filter by kind / sheet_name)
- `GET /api/runs/{id}/sheets` — sheet names for a run
- `GET /api/runs/{id}/report` — download the generated `.xlsx`
- `POST /api/runs/{id}/rerun` — re-queue a past run's exact input files
- `PATCH /api/runs/{id}/results/{result_id}/annotate` — acknowledge/resolve/note an exception row

### Admin (admin role required)
- `GET /api/admin/module-configs` / `PUT /api/admin/module-configs/{module_key}` — org-level default options
- `GET|POST /api/api-keys`, `DELETE /api/api-keys/{id}` — service-to-service credentials
- `GET|POST /api/schedules`, `PATCH|DELETE /api/schedules/{id}` — recurring schedules

## 🚀 Getting Started

### Prerequisites
- Docker + Docker Compose (recommended path), **or** Python 3.11+ and Node.js 18+ for local dev without Docker

### Quick start — Docker Compose

```bash
git clone <this-repo>
cd Reconciliation_OS
docker compose up --build
```

Scale worker capacity independently of the API tier for large batches (e.g. UPI's 500-file NTSL uploads):

```bash
docker compose up --scale worker=4
```

### Local dev without Docker

**Backend** (zero extra infra — SQLite + an in-process thread pool instead of Postgres/Redis/Celery):

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
JOB_RUNNER=inprocess DATABASE_URL="sqlite:///./recon_os.db" uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to `http://localhost:8000` (`frontend/vite.config.ts`) — no CORS setup needed for local dev.

**Tests:**

```bash
cd backend && source .venv/bin/activate && python3 -m pytest -q
```

**Load test** (500 synthetic UPI files + 150 RuPay files, ~3s total):

```bash
cd backend && source .venv/bin/activate && PYTHONPATH=. python scripts/load_test.py
```

## 🔑 Environment Variables

See [`backend/.env.example`](backend/.env.example) for the full annotated list. Highlights:

```bash
DATABASE_URL=postgresql+psycopg2://recon:recon@postgres:5432/recon_os

# Off by default - no login screen; set true for shared/exposed infra
AUTH_REQUIRED=false
JWT_SECRET=change-me-in-production

# inprocess = zero-infra thread pool | celery = production worker pool
JOB_RUNNER=celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1

# none (default) | email | slack | both
NOTIFY_BACKEND=none
SLACK_WEBHOOK_URL=
```

## 🔢 Ports

Every service gets its own, non-overlapping port — no two services in this stack ever share a host port:

| Service | Port | Purpose |
|---|---|---|
| Frontend | `5173` | React app (dev server, or nginx in Docker) |
| Backend | `8000` | FastAPI + interactive docs at `/docs` |
| PostgreSQL | `5432` | Primary database |
| Redis | `6379` | Celery broker + result backend |

(`worker` and `beat` are background processes with no exposed port.)

## 🧠 Core Features Breakdown

### Module coverage

| Module | Source tool | Key | Status |
|---|---|---|---|
| NFS Settlement Recon | `NFS_Recon_Tool_v5.html` | `nfs` | ✅ Full port + tests |
| RuPay Recon | `Rupay_Recon_Utility_v4_1.html` | `rupay` | ✅ Full port + tests |
| UPI NTSL Recon | `UPI_Recon_Utility.html` | `upi` | ✅ Full port + tests |
| NETC FASTag Recon | `Fastag_Recon_Tool_v2_90file.html` | `fastag` | ✅ Full port + tests |
| Payment Gateway Recon (Ops/PayU/Cashfree) | `ReconModule.bas` | `pg_recon` | ✅ Full port + tests, validated against real sample data |
| Bank vs Add Money Recon | `Bank_vs_Add_Money...bas` (bug-fixed) | `bank_addmoney` | ✅ Full port + tests |
| 6F/6R Data Preparation | `app.py` (Streamlit) | `data_prep_6f` | ✅ Full port + tests |

### Run lifecycle

`created → queued → parsing → validating → matching → reporting → completed | failed`, persisted as `RunEvent` transitions for a full audit trail. A best-effort email/Slack notification fires on `completed` and `failed`.

### Recurring schedules

Any completed run can be turned into a schedule (🔁 button on the run's detail page). A Celery-beat process polls every 60 seconds and re-fires due schedules by cloning the source run's exact input files into a new run — no manual re-upload for a recon that runs the same way every night.

## 🔐 Security Features

- ✅ Password hashing with bcrypt (direct, SHA-256 pre-hashed for bcrypt's 72-byte limit)
- ✅ API keys hashed with SHA-256 (appropriate for high-entropy server-generated tokens, unlike low-entropy human passwords)
- ✅ JWT authentication, off by default; ownership checks on every run (`triggered_by` vs. requesting user, unless admin)
- ✅ Content-sniffed file format detection (magic bytes, not trusted extensions — NPCI's `.xls` exports are actually HTML)
- ✅ Admin-only routes (`require_admin` dependency) for module defaults, API keys, and org-wide settings
- ✅ File upload validation (extension allowlist per input slot, size limits)

## 📈 Performance & Scalability

- **Async job execution**: uploads return immediately; reconciliation runs in a Celery worker pool (horizontally scalable via `docker compose up --scale worker=N`) or a local thread pool for zero-infra dev
- **Load-tested**: 500 synthetic UPI NTSL files end-to-end in 2.3s (100% match rate, 0 errors); 150 RuPay DSR files in 0.6s
- **Plugin architecture**: the engine (`app/recon/engine.py`) has zero module-specific logic — adding an 8th reconciliation type never touches the engine, API layer, or frontend shell

## 📝 Example Workflow

1. **Upload & run**
   ```
   POST /api/runs
   Content-Type: multipart/form-data
   module_key=nfs, options={"threshold": 1.0}, ntsl=[...files], bank=[...file]
   ```
   → `201 Created`, run status `queued`, picked up by a worker within milliseconds

2. **Poll for completion**
   ```
   GET /api/runs/{id}
   ```
   → status progresses through `parsing → validating → matching → reporting → completed`

3. **Review results**
   ```
   GET /api/runs/{id}/results?kind=exception
   ```
   → every mismatched row, with an `annotation_status` an analyst can set via the UI

4. **Export or schedule**
   ```
   GET /api/runs/{id}/report          # download the .xlsx
   POST /api/schedules                # or: turn this exact run into a nightly job
   ```

## 🚧 Known Limitations

- NFS/UPI/RuPay/FASTag parsing is validated against synthetic fixtures matching the documented file format, not real production NPCI/bank exports yet — see [`docs/KNOWN_DEVIATIONS.md`](docs/KNOWN_DEVIATIONS.md) for the exact scope and every deliberately-preserved behavioral quirk carried over from the original tools.
- No dark mode or run-to-run comparison view yet (both scoped, not started).
- Live status updates poll every 1.5s rather than push over a websocket/SSE stream.

## 📚 Further Reading

- [`docs/PRD.md`](docs/PRD.md) — full product requirements, per-module functional spec
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — tech stack rationale, data model, API contract, deployment topology
- [`docs/KNOWN_DEVIATIONS.md`](docs/KNOWN_DEVIATIONS.md) — every place ported behavior differs from a literal copy of the original tools, and why
- [`CHANGELOG.md`](CHANGELOG.md) — release history

## 🗂️ Repository Layout

```
docs/              PRD.md, ARCHITECTURE.md, KNOWN_DEVIATIONS.md
backend/
  app/
    core/          config, db, security, storage, job runner, notify
    models/        SQLAlchemy models
    schemas/       Pydantic API schemas
    api/           FastAPI routers (auth, modules, runs, admin, api-keys, schedules)
    recon/         base contract, engine, registry, shared utils, the 7 modules
    workers/       Celery app, task, beat (recurring schedules)
  tests/           pytest suite (one file per module + engine/beat/notifier contract tests)
  alembic/         DB migrations
  scripts/         load_test.py
frontend/
  src/
    api/           typed fetch client
    context/       auth + toast context
    pages/         Dashboard, ModuleRun, RunDetail, RunHistory, Admin, Login
    components/    Layout, FileDropzone, DataTable, ValidationPanel, RunsTrendChart, ...
docker-compose.yml
```

## 🤝 Contributing

Internal Eroute Technologies tool. For bugs, feature requests, or access to real sample files for NFS/UPI/RuPay/FASTag validation, reach out to the project owner directly.

## ⚖️ License

Proprietary — internal use within Eroute Technologies only. Not licensed for external distribution.

---

**Last Updated:** 2026-07-29 · **Current Phase:** Fast-follow batch complete — production core + scheduling/admin/notifications
