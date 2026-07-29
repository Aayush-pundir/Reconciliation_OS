# Recon OS

**Unified Reconciliation Platform for Eroute Technologies.** One web app replacing seven independent tools (5 offline HTML utilities, 2 VBA macros, 1 Streamlit script) with a single upload → reconcile → review → export flow, backed by persisted run history and an audit trail.

- Full requirements: [`docs/PRD.md`](docs/PRD.md)
- Architecture, data model, API contract: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Stack

Python 3.11 / FastAPI / SQLAlchemy / Celery+Redis / PostgreSQL backend, React 18 / TypeScript / Vite / Tailwind frontend. Rationale for every choice is in `ARCHITECTURE.md §1`.

## Quick start (Docker Compose)

```bash
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend + API docs: http://localhost:8000/docs
- Seeded login: `admin@eroute.local` / `ChangeMe123!` — **change this before any real deployment.**

Scale worker capacity for large batches (e.g. UPI's 500-file NTSL uploads) independently of the API tier:

```bash
docker compose up --scale worker=4
```

## Local dev without Docker

**Backend** (zero extra infra — uses SQLite + an in-process thread pool instead of Postgres/Redis/Celery):

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
JOB_RUNNER=inprocess DATABASE_URL="sqlite:///./recon_os.db" uvicorn app.main:app --reload
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to `http://localhost:8000` (see `frontend/vite.config.ts`) — no CORS setup needed for local dev.

**Tests:**

```bash
cd backend && source .venv/bin/activate && python3 -m pytest -q
```

33 tests, all passing — one regression suite per module plus an engine contract test. The PG Recon suite runs against the exact 15-row Ops/PayU/Cashfree sample data shipped inside the original `Reconciliation_Tool.xlsm`.

## Module coverage

Every module below is a full, faithful port of its source tool's business logic — filename patterns, fee formulas, matching tolerances, validation passes, and Excel output all preserved (see `PRD.md §7` for the exact, line-by-line requirement each module implements).

| Module | Source tool | Key | Status |
|---|---|---|---|
| NFS Settlement Recon | `NFS_Recon_Tool_v5.html` | `nfs` | ✅ Full port + tests |
| RuPay Recon | `Rupay_Recon_Utility_v4_1.html` | `rupay` | ✅ Full port + tests |
| UPI NTSL Recon | `UPI_Recon_Utility.html` | `upi` | ✅ Full port + tests |
| NETC FASTag Recon | `Fastag_Recon_Tool_v2_90file.html` | `fastag` | ✅ Full port + tests |
| Payment Gateway Recon (Ops/PayU/Cashfree) | `ReconModule.bas` | `pg_recon` | ✅ Full port + tests |
| Bank vs Add Money Recon | `Bank_vs_Add_Money...bas` (bug-fixed version) | `bank_addmoney` | ✅ Full port + tests |
| 6F/6R Data Preparation | `app.py` (Streamlit, latest version) | `data_prep_6f` | ✅ Full port + tests |

### Deliberate, disclosed simplifications (see inline docstrings in each module)

- **Excel header presentation**: the original NFS/RuPay/UPI exports used 3-row merged spreadsheet-letter headers (e.g. column `E` under group "NPCI Assessment Fees" > "POS" > "Amount"). Recon OS uses single, descriptively-named columns instead (e.g. `NPCI Assess POS`) — same data, one header row, easier to read. No field from any source tool's output is dropped.
- **NFS's dual settlement-total figures**: the original tool computes both the NTSL's own stated total and an independently-recomputed one from fee formulas, and uses them in different places (on-screen status vs. the exported Excel's live formula). Both numbers are preserved and exposed separately — see the docstring in `app/recon/modules/nfs.py`.
- **6F's input model**: the original Streamlit tool read from a server-local folder path (it ran on the analyst's own machine). Recon OS runs server-side behind a browser client, so the input is direct multi-file upload instead — every classification/filter rule is unchanged.
- **Live status updates** use 1.5s client-side polling rather than a websocket/SSE stream. The `Run`/`RunEvent` data model already carries everything a push-based stream would need; wiring one up is a mechanical fast-follow, not a data-model change.
- **Auth** is a minimal local email/password + JWT implementation (two roles: `analyst`, `admin`) — sufficient for an internal tool per the PRD's non-goals; SSO integration is called out as an open question in `PRD.md §15`.

### What's new versus the seven original tools

Run history and audit trail, async server-side processing (no more browser tab freezing on large batches), a single consistent UI across all seven reconciliation types, persisted structured results queryable independent of the Excel file, and a plugin architecture where adding an eighth reconciliation type is one new Python file plus one registration line — no other code changes (`ARCHITECTURE.md §4.1`).

## Repository layout

```
docs/            PRD.md, ARCHITECTURE.md
backend/
  app/
    core/        config, db, security, storage, job runner
    models/      SQLAlchemy models
    schemas/     Pydantic API schemas
    api/         FastAPI routers (auth, modules, runs)
    recon/       base contract, engine, registry, shared utils, the 7 modules
    workers/     Celery app + task
  tests/         pytest suite (one file per module + engine contract test)
  alembic/       DB migrations
frontend/
  src/
    api/         typed fetch client
    context/     auth context
    pages/       Dashboard, ModuleRun, RunDetail, RunHistory, Login
    components/  Layout, FileDropzone, DataTable, ValidationPanel, ...
docker-compose.yml
```
