# Recon OS — Product Requirements Document

| | |
|---|---|
| **Product** | Recon OS — Unified Reconciliation Platform |
| **Owner** | Eroute Technologies — Finance Systems |
| **Status** | v1.0 Draft → Build |
| **Author** | Product/Engineering (AI-assisted) |
| **Date** | 2026-07-29 |

---

## 1. Executive Summary

Eroute Technologies runs settlement reconciliation across seven independent, hand-built tools: five single-file offline HTML utilities (NFS, RuPay, UPI, FASTag, and a legacy NFS variant), one Excel/VBA macro pair (Payment Gateway Ops-vs-PayU-vs-Cashfree, and Bank-vs-Add-Money), and one Streamlit script (6F data preparation). Each was built independently, has its own UI conventions, its own copy of SheetJS/ExcelJS, its own bugs, and produces its own differently-shaped Excel report. None of them retain history, none of them talk to each other, and none of them can be operated by anyone other than the person who has the file on their laptop.

**Recon OS** replaces all seven with one web application: one upload flow, one job engine, one results experience, one audit trail — while treating every reconciliation rule already encoded in those tools as a **hard requirement**, not a suggestion. Nothing that currently reconciles correctly is allowed to reconcile differently after migration.

## 2. Problem Statement

- **Fragmentation**: 7 tools, 7 UIs, 7 copies of the same 40MB JS libraries, no shared code.
- **No history**: every run is stateless — close the tab, lose the result. Reruns for audits mean re-uploading everything from scratch.
- **No collaboration**: single-laptop, single-file tools. No way for a manager to see what an analyst ran, or to compare this month's exceptions to last month's.
- **Scale ceiling**: browser-based parsing chokes past a few hundred files (UPI alone expects up to 500 NTSL files); everything runs on the main thread with manual `yield()` calls to avoid freezing the tab.
- **Correctness risk**: business logic (fee formulas, UTR-extraction regexes, matching tolerances) lives only inside minified/inline JS or VBA with no tests, no version control, no code review. We already found and fixed two live bugs in the VBA macros during this project (a Python-syntax typo that aborted every run, and a resource-leak on early-exit).
- **No auditability**: reconciliation is a finance-compliance function; "I ran it on my laptop last Tuesday" is not an audit trail.

## 3. Vision

One reconciliation operating system: analysts drag files into a module, the system validates, reconciles, and reports — consistently, on a server, with every run persisted, versioned, and re-downloadable. New settlement rails (a new card network, a new PG) become a new **module** behind a stable plugin interface, not a new standalone tool.

## 4. Goals

1. **Zero regression** — every rule, formula, tolerance, filename pattern, and Excel output structure from the seven source tools is preserved exactly (see §7, per-module functional specs, marked **[MANDATORY]**).
2. **One platform** — a single web app (backend API + frontend SPA) hosts all seven recon types as modules behind a common run lifecycle: upload → validate → reconcile → review → export.
3. **Run history & audit** — every run, its inputs, its outputs, and who triggered it are persisted and re-viewable/re-downloadable indefinitely.
4. **Scale beyond the browser** — file parsing and reconciliation run server-side, async, queued, horizontally scalable; 500+ file batches must not degrade the UI.
5. **Extensibility** — adding an 8th recon type requires implementing one Python interface (`ReconModule`) and registering it; no changes to routing, storage, job orchestration, or the frontend shell.
6. **Professional UX** — one visual language, one interaction pattern, replacing seven inconsistent hand-rolled UIs (dark amber, navy, blue/white, dark slate...).

## 5. Non-Goals (v1)

- Real-time streaming bank-feed ingestion (all inputs remain file uploads).
- Multi-tenant SaaS for external customers — this is an internal Eroute Technologies tool (single org, role-based users).
- Automated ERP/accounting-system posting of reconciled entries (export to Excel remains the terminal action, same as today).
- Mobile app (responsive web is sufficient; this is a back-office finance tool).
- Replacing the *decision* to escalate an exception — Recon OS surfaces exceptions; humans still action them (email/ticket integration is a fast-follow, not v1).

## 6. Personas

| Persona | Need |
|---|---|
| **Reconciliation Analyst** (daily user) | Upload the day's/month's files for a given rail, get matched/unmatched/exception breakdown fast, download the Excel for records, without needing to know the underlying fee formulas. |
| **Finance Manager** | See recon status across all rails at a glance, drill into any past run, spot trends in exception volume, run comparisons month-over-month. |
| **Finance Systems / Ops Engineer** (this team) | Add/modify a recon module without touching unrelated code; trust that a rule change is tested and reviewed like any other code change. |
| **Auditor** (periodic) | Pull up any historical run, see exactly what inputs produced what output, with no possibility the source files or logic have silently changed since. |

## 7. Functional Requirements — Per Recon Module

Every requirement below is a direct, faithful port of logic already read out of the source tools. These are **[MANDATORY]** — v1 does not ship a module until its checklist is fully implemented and unit-tested.

### 7.1 Module: NFS Settlement Recon *(from NFS_Recon_Tool_v5)*

- **Inputs**: NTSL files — any of `.xls/.xlsx/.xlsm`, either NPCI's HTML-formatted "XLS" export or a real OOXML/binary workbook, individual files or one merged workbook containing many settlement blocks. Format is content-sniffed (ZIP magic `PK\x03\x04` → OOXML; OLE magic `D0CF11E0` → binary XLS; else HTML). Plus one bank statement workbook.
- Cycle identity: from filename pattern `NTSLERODDMMYY_NC` when present; otherwise assigned `C1..C4` by block order within a date, taken from the "Daily Settlement Statement ... as on DD/MM/YYYY" header (also accepts `DD-MM-YYYY`, `YYYY-MM-DD`, `DD MMM YYYY`).
- Per-block extraction: Final Settlement Amount; Issuer WDL (ATM) transaction amount + count; Issuer WDL Approved Fee; Micro-ATM transaction amount + count (the "Rs. 100 and above" row specifically); Issuer BI (balance-inquiry) approved-fee count; Dispute Adjustments → "Adjustment Sub Totals" (debit − credit).
- Fee formulas (must match exactly):
  - ATM fee = parsed fee if present and non-zero, else `count × ₹19`; ATM GST = `fee × 18%`; ATM total = `fee + GST`.
  - BI fee = `count × ₹6`; GST = `fee × 18%`; total = `fee + GST`.
  - Micro-ATM fee = `amount × 0.5%`; GST = `fee × 18%`; total = `fee + GST`.
  - Switching count = `ATM count + BI count + Micro count`; switching fee = `count × ₹0.30`; GST = `fee × 18%`; total = `fee + GST`.
  - Settlement total = `ATM amt + ATM total-fee + Micro amt + Micro total-fee + Switching total-fee − Dispute amt + BI total-fee`.
- Bank match key: narrative containing `_00YYYYMMDDCC`, remarks column = `NFS`. Match tolerance configurable, default **₹1**.
- Statuses: `MATCHED`, `PENDING` (no bank entry yet — expected T+1), `EXCESS DEBIT`, `DEFICIT`.
- Daily aggregation (sum of cycles per date) with its own MATCHED/PENDING/DEFICIT/EXCESS/PARTIAL rollup.
- Carry-over: bank entries whose settlement month falls outside the loaded NTSL month(s) — tracked separately, excluded from recon totals, shown as an audit trail.
- Output: Excel with `NFS_Recon_Cycle` (merged 3-row header, frozen panes, one row per cycle, live `SUBTOTAL` grand-total row), `Daily_Summary`, `Exceptions`, and `Carry_Over` (only if non-empty) sheets.
- Re-import: a previously exported `NFS_Recon_*.xlsx` can be re-loaded to review without re-running raw files. *(Superseded in Recon OS by persisted run history — see §9 — but the parser for re-import format is retained for one-time migration of legacy exports.)*

### 7.2 Module: RuPay Recon *(from Rupay_Recon_Utility_v4_1)*

- **Inputs**: up to 150 DSR summary files named `ISSUER_YYYY-MM-DD-C` (`C` = cycle 1–4), plus one bank statement.
- Row classification requires tracking running context columns down the sheet: BIN (col E), status (col G, `A`/`D`), transaction cycle (col H).
- BIN `818014` routes to the **Gift Card** bucket (POS-GC / ECOM-GC) instead of standard POS/ECOM.
- Presentment types counted: `Presentment (With Auth)`, `Offline Presentment(Without Auth)`, transaction type `Purchase`, status ≠ Declined.
- Buckets tracked per channel (POS/ECOM/Cash-at-POS/POS-GC/ECOM-GC): counts, settlement amounts, interchange income, NPCI assessment fees, NPCI processing fees (from `DMS Auth Transaction` rows, status Approved, excluding `Balance Update` and qSPARC, where settlement credit = 0 and another debit > 0), refunds, qSPARC-load settlements, chargebacks (raise + acceptance), re-presentment raised, DMS open/unauthorized items.
- GST taken verbatim from the `INWARD GST` row; **net settlement taken verbatim from the DSR grand-total row** (`Total/Total/Total/Total/Total`), never recomputed — this avoids rounding drift against the bank.
- **Triple validation** (all three must run on every file set):
  1. `total_fees × 18% ≈ GST` (±₹0.10).
  2. Recomputed net settlement equals DSR's own grand total (±₹0.01).
  3. Grand total is non-zero whenever POS/ECOM/qSPARC settlements are non-zero.
- Bank match key: narrative regex `_00YYYYMMDDCC`, excluding narratives containing `Rev_`.
- Output: single "Rupay Control Sheet_<Month>" workbook, 60 columns wide, 3-row merged group/sub-group/column headers (rows 5–7), frozen panes, per-row conditional fill (green if `|diff| < ₹1`, red otherwise), totals row with live `SUM` formulas.

### 7.3 Module: UPI NTSL Recon *(from UPI_Recon_Utility)*

- **Inputs**: NTSL folder, filenames `UPI_NTSLERT{DDMMYY}_{CYCLE}.xls/.xlsx/.xlsm/.xlsb`, up to 500 files; bank statement `.xlsx/.xls/.xlsm/.xlsb/.csv`.
- 12 settlement cycles: `10C, 1C–9C, DC1, DC2`. T-cycles (same-day) = `3C–9C`. T+1 cycles = `10C, 1C, 2C, DC1, DC2`.
- Parse header row 3 pattern `as on DD-MM-YYYY (CYCLE HH:MM:SS`, fallback to filename. Column indices auto-detected from row 5 headers (description/count/debit/credit) with hard-coded fallback positions.
- Row classifier (regex, in priority order): TDS → GST on Penalty → Penalty → Net Adjusted Amount → Transaction Amount → Switching Fee GST → Switching Fee → Approved Fee GST → Approved Fee. Rows matching `total|grand|sub.?total|net settlement|settlement amount|opening|closing` are skipped. `DC1`/`DC2` files keep only Net Adjusted Amount / Penalty / GST-on-Penalty / TDS rows.
- Bank narrative parser: **5 fallback regex patterns**, applied in order, covering variants of `Eroute UPI Setl {CYCLE} {DDMMYY}`, `DC0{N} UPI ... NPCI00{date}`, and `NPCI00{date}{cycle}` suffix forms, with a cycle-code → cycle-label map for 2-digit suffixes.
- Prior-month carryover: bank rows dated before the earliest loaded NTSL date are bucketed as `Prior Month Carryover`, excluded from primary match stats, still reported.
- Matching tolerance: **₹1.0**.
- **Three-pass validation**, each independently re-deriving its own numbers rather than trusting the primary computation:
  1. *Input Integrity* — file count sanity, filename-pattern conformance %, per-date 12-cycle coverage completeness, duplicate-filename detection, bank file presence.
  2. *Data Integrity* — zero-value row detection, independent recomputation of every cycle's net (credit − debit) compared to the stored value, grand-total cross-check (row-level sum vs cycle-sum), Remarks-classification coverage.
  3. *Reconciliation Integrity* — bank-narrative parse success rate, independent re-match verification, discrepancy count at tolerance, grand-total bank-vs-NTSL gap, overall match rate.
- Output: 6-sheet workbook — `Working` (raw classified rows), `Settlement Recon` (per-cycle), `Bank Recon` (matched + separated prior-month section), `Daily Summary` (T vs T+1 split), `Pivot` (category × debit/credit), `Insights` (multi-section narrative: overall summary, key findings, cycle-wise monthly net, daily net).

### 7.4 Module: NETC FASTag Recon *(from Fastag_Recon_Tool_v2)*

- **Inputs**: DSR folder (recursive), one file = one settlement block/cycle, `.xlsx/.xls`; bank statement.
- Header row located by `col0 == 'Settlement Date'`; block date = first non-null value after header. Files are filename-sorted before parsing so NPCI cycle order is preserved; cycle number assigned per date by parse order.
- Extraction: `INWARD GST` sub-row; grand-total row (`col1=='Total' AND col4=='Total'`); `DEBIT` rows where category is `TOLL` or `PARKING`, summed for count/amount.
- `taxable = serviceTotal − gst`; `net = grandTotal[col27]`.
- Bank narrative split on `_00` → 8-digit date + cycle suffix.
- **Two-pass matching**: (1) direct `date|cycle` key match; (2) for any DSR block still unmatched with non-zero net, search bank entries of the **same cycle number** not yet consumed for an amount match (±₹0.01) — flags `Matched – Narrative Mismatch*` (amount correct, bank narrative carries the wrong date).
- Statuses: `Matched`, `Matched – Narrative Mismatch`, `Zero DSR – No Debit`, `Pending – Next Month Debit` (only for the last loaded date), `Unmatched – Investigate`.
- Reconciliation bridge: `Bank Total Debited + Pending Next Month` vs `DSR Net Payable`, tolerance ₹0.05.
- Output: 3-sheet workbook — `Recon Detail`, `Summary`, `Exceptions` (4 sub-sections: Unmatched / Narrative Mismatch / Pending / Zero).

### 7.5 Module: Payment Gateway Recon — Ops vs PayU vs Cashfree *(from ReconModule.bas)*

- **Inputs**: three tables — Ops (`Transaction ID`, `Status`), PayU (`txnid`, `status`), Cashfree (`Order Id`, `Transaction Status`) — headers located dynamically by name, not fixed column position.
- Key normalization: uppercase, trimmed, **must start with `TRX`** or the row is ignored for matching purposes.
- Rule engine mapping the `(Ops status, PayU status, Cashfree status)` triple to one of six actions — **Successfully Completed, Refund, Failed, Cancelled, To Check, Manual Check Required** — via an explicit, ordered rule table (ported verbatim from the VBA `DetermineAction` function, including its extended/inferred rules and its fallback), each carrying a fixed explanatory remark where applicable.
- Coverage tagging per Ops row: `Ops + PayU + CF`, `Ops + PayU only`, `Ops + CF only`, `Ops only`.
- **Orphan passes**: PayU transactions absent from Ops → `Manual Check Required` / `PayU only`; Cashfree transactions absent from both Ops and PayU → `Manual Check Required` / `CF only`.
- Output: reconciliation table (one row per unique transaction key across all three sources) + summary (action counts & %, coverage counts & %, run timestamp), colour-coded identically to the original 6-colour scheme.

### 7.6 Module: Bank vs Add Money Recon *(from the corrected Bank_vs_Add_Money .bas)*

- **Inputs**: Ops table (`TransactionCategory`, `TransactionType`, `UtrNo`, `TotalTransactionAmount`, `EnterpriseName`); Bank table (`Narrative`, `Credit`).
- Ops filter: `TransactionCategory ∈ {ADD MONEY, OPS ADJUSTMENT, OPS ADJUSTEMENT}` **and** `TransactionType == CREDIT`.
- UTR extraction from Ops: `TRXV*` → row excluded entirely; `RE1*` → strip first 3 characters; else → all numeric digits extracted from the raw value.
- UTR extraction from Bank narrative, by prefix (checked in this order): `IMPS/` → first 12 digits; `IFT/` → first 11 digits; `INEFT`/`IRTGS` → digits between `~EROUTE~` and the next `~`; `NEFT`/`RTGS`/`IMPS` without a slash → digits between the 1st and 2nd `/`; else → all digits (fallback).
- Aggregation: duplicate UTRs on either side are summed, not treated as separate rows.
- Match tolerance: **₹0.01**. Statuses: `MATCHED`, `AMOUNT MISMATCH`, `NOT IN BANK`, `NOT IN OPS`.
- Output: reconciliation table (`Final UTR, Enterprise Name, Ops Amount, Bank Amount, Difference, Status`) + summary block (counts by status, matched-amount totals, net unreconciled difference), 4-colour scheme.

### 7.7 Module: 6F/6R Data Preparation *(from the Streamlit app.py, latest version)*

- **Inputs**: one or more folder paths (v1 web equivalent: multi-file upload, since Recon OS has no server-local folder access from a browser client), files typed by name/size: `GIFT*` → GIFT, `NCMC*` → NCMC, size `> 10MB` → NORMAL, else `UNKNOWN` (skipped, reported with reason).
- Per type, **every sheet in every workbook** (not just the first) is scanned; a sheet is kept only if it contains the full required-column set for that type (`Status, TransactionCategory, TransactionDate, TransactionType, Amount` for NORMAL/GIFT; `SETTLEMENTDATE, SETTLEMENTAMT, TRXN_TYPE` for NCMC). CSV = single implicit sheet.
- NORMAL & GIFT: filter `Status == "completed"` (case-insensitive), exclude rows whose `TransactionCategory` contains `"reversal"` (case-insensitive) — this is the **updated** exclusion token, superseding the older `"refund"` token found in the prior version.
- NCMC: no status filter; `SETTLEMENTDATE` parsed as `YYYYMMDD`.
- Aggregation: pivot to `Date × {Credit,Debit}-{Normal,NCMC,Gifted}` — 7 columns (`Date` + 6 metric columns), sorted chronologically.
- Skipped/errored files reported with a reason string.
- Output: single-sheet `6F_Report` workbook.

## 8. Cross-Cutting Functional Requirements (the shared engine)

These are new capabilities Recon OS adds on top of the seven modules — the actual point of building "one platform."

- **F1 — Module registry.** The set of available recon types is data-driven (a registry of `ReconModule` implementations), not hard-coded routing. The frontend renders the module list, its required input slots, and its options from a schema the backend serves.
- **F2 — Run lifecycle.** Every reconciliation is a **Run**: `created → uploading → queued → parsing → validating → matching → reporting → completed | failed`. State is persisted at every transition; the frontend polls/subscribes for live status.
- **F3 — Async, queued processing.** Runs execute on a background worker pool, not the request thread. A run of 500 files must not block the API or the browser.
- **F4 — Idempotent re-run.** Any past run's exact input file set can be re-queued (e.g., after a module bug-fix) without re-uploading.
- **F5 — Persisted results.** Every run's structured results (summary stats, per-row detail, exceptions, validation findings) are stored queryable in the database, not only inside a generated Excel — enabling in-app tables, filtering, and future cross-run analytics without re-parsing files.
- **F6 — Excel export parity.** Every module's Excel output structure (sheet names, headers, colours, formulas where the source used live formulas) is reproduced byte-for-byte-equivalent in content to its source tool, generated server-side with `openpyxl`.
- **F7 — Validation surfacing.** Any module that runs multi-pass validation (RuPay's triple validation, UPI's 3-pass) surfaces each pass and each check as a discrete, individually pass/warn/fail item in the UI — not collapsed into one boolean.
- **F8 — Run history & search.** List/filter/search past runs by module, date range, status, uploader.
- **F9 — Audit trail.** Every run records: who triggered it, exact input files (content-hashed), module version/logic-hash used, timestamps for every lifecycle transition, and the final output artifact. Nothing is mutable after `completed`.
- **F10 — RBAC.** Two roles for v1: `analyst` (upload, run, view own + team runs, download) and `admin` (all of the above + user management + module configuration, e.g. adjusting default tolerances).
- **F11 — File validation feedback.** Before a run is queued, the UI shows per-file validation (filename pattern match, extension, size) exactly as today's tools do (green ✓ / red ✗ chips), so bad uploads are caught pre-flight, not mid-run.

## 9. Non-Functional Requirements

| Category | Requirement |
|---|---|
| **Scalability** | Horizontally scalable workers; a run of 500 files (UPI's stated ceiling) must complete without degrading other concurrent runs. Stateless API layer behind a load balancer. |
| **Performance** | Per-file parse time budget: comparable to or better than today's browser tools (NFS: ~100ms/file HTML parse observed). Run status must update within 2s of a state transition (poll or push). |
| **Reliability** | A worker crash mid-run must not corrupt run state — runs resume or cleanly fail-with-reason, never hang in `processing` forever (timeout + dead-letter handling). |
| **Data integrity** | Uploaded source files are retained (content-addressed storage) for the run's retention period so results are always re-derivable and auditable. |
| **Security** | All uploads and downloads authenticated. Files and DB at rest encrypted (managed by infra — Postgres + object storage encryption). No secrets in source. |
| **Observability** | Structured logs per run/module; failed runs capture full stack trace + input file manifest for debugging without needing to reproduce locally. |
| **Portability** | Fully containerized (Docker Compose for dev/small-prod; same images deployable to any container orchestrator). |
| **Extensibility** | New module = new Python class + registration; zero changes to core routing, job orchestration, storage, or frontend shell (module UI is schema-driven). |

## 10. Information Architecture / UX

**Design principle**: one visual system across all seven modules (the source tools ranged from dark-amber to navy to light-blue — none of that survives). Calm, data-dense, finance-tool aesthetic: neutral surface, one accent colour, status colours reserved strictly for match/exception states (green/amber/red), monospace for money and codes.

**Screens**:
1. **Dashboard** — tiles per module (icon, name, last-run status, quick "Run" CTA) + a cross-module recent-runs feed + KPI strip (open exceptions across all modules today).
2. **Module Run** (dynamic per module, driven by its input schema) — upload zones matching the module's declared input slots (e.g. NFS: NTSL zone + Bank zone; PG Recon: Ops/PayU/Cashfree zones), pre-flight per-file validation chips, run options (tolerance override, month filter), "Run Reconciliation" CTA.
3. **Run Detail / Results** — status header (progress through lifecycle stages), KPI stat row (module-specific, mirrors each tool's original stat grid), tabbed results (Summary / Detail / Exceptions / Validation — tabs present only if the module produces that data, e.g. only RuPay/UPI show a Validation tab), searchable/sortable data tables, "Download Excel" CTA.
4. **Run History** — filterable/searchable table of all runs (module, date, status, triggered-by, exception count), click-through to Run Detail.
5. **Admin** — user list/roles, module default-tolerance configuration.

## 11. High-Level Data Model

- `User(id, email, name, role)`
- `ReconModule` — not a DB table; a code registry entry (`key, display_name, icon, input_slots[], options_schema, version`).
- `Run(id, module_key, status, triggered_by, options_json, created_at, started_at, completed_at, error_message)`
- `RunFile(id, run_id, slot, original_filename, content_hash, size_bytes, storage_path, validation_ok, validation_note)`
- `RunResult(id, run_id, kind[summary|detail|exception|validation], sheet_name, payload_json)` — structured, queryable result rows, one family per module's output sections.
- `RunArtifact(id, run_id, kind[excel_report], storage_path, generated_at)`

(Full schema with columns/types/constraints lives in `ARCHITECTURE.md` §Data Model.)

## 12. API Surface (summary — full contract in `ARCHITECTURE.md`)

- `GET /api/modules` — list registered modules + their input/options schema.
- `POST /api/runs` — create a run for a module (multipart upload of all input slots + options).
- `GET /api/runs` — list/filter/search runs.
- `GET /api/runs/{id}` — run detail + status.
- `GET /api/runs/{id}/results?kind=` — paginated structured results.
- `GET /api/runs/{id}/report` — download the generated Excel artifact.
- `POST /api/runs/{id}/rerun` — re-queue with the same inputs.
- `WS /api/runs/{id}/events` (or polling fallback) — live status stream.

## 13. Milestones

| Phase | Scope |
|---|---|
| **M0 — Foundation** | Repo scaffold, backend core (module registry, run lifecycle, storage, job runner), frontend shell, Docker Compose. |
| **M1 — Module parity** | All seven modules implemented and unit-tested against the extracted rule sets in §7. |
| **M2 — Unified UX** | Full frontend: dashboard, dynamic run wizard, results viewer, history, admin. |
| **M3 — Hardening** | Auth/RBAC, audit trail completeness, load-tested against 500-file batches, observability. |
| **M4 — Fast-follows** | Cross-run analytics/trends, notification integrations (email/ticket on exception), server-side folder ingestion for 6F, legacy-export re-import migration tool. |

This build covers **M0–M2** in full and lays the concrete groundwork (auth scaffolding, module-version hashing, structured logging hooks) for **M3**.

## 14. Success Metrics

- 100% of the seven tools' reconciliation logic reproduced with zero behavioral diffs (validated by unit tests ported from each tool's known-good sample data, e.g. the VBA workbook's 15-row sample set).
- Time-to-result for a standard monthly UPI batch (≈360 files) reduced vs. browser-based parsing, with the UI remaining responsive throughout.
- Every run since go-live retrievable in ≤2 clicks from the dashboard.
- Zero "lost result" incidents (today: any closed browser tab = lost result).

## 15. Risks & Open Questions

- **Risk**: Excel formula-fidelity (live `SUM`/`SUBTOTAL` formulas in NFS/RuPay/UPI outputs) — `openpyxl` supports writing formulas as text; Excel recalculates on open, so parity is achievable but must be explicitly tested (a formula string with a typo silently becomes a stored string, not an error, until opened in Excel).
- **Risk**: HTML-as-XLS NTSL parsing depended on hand-tuned regexes over raw HTML in the original tool; the Python port uses a proper HTML table parser (more robust) but must be validated against real NPCI export samples before cutover.
- **Open question**: retention period for uploaded source files (compliance requirement — assumed 7 years to match typical Indian financial record-keeping norms; confirm with Finance).
- **Open question**: whether 6F's "folder path" input model should be replaced by upload-only (assumed yes for v1, since a browser cannot read a server-local folder path) or whether a companion CLI/agent for server-side folder ingestion is required as a fast-follow.
- **Open question**: SSO — v1 assumes local email/password auth; confirm if Eroute has an existing IdP to integrate instead.
