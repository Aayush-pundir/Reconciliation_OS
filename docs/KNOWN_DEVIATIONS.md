# Known Deviations from the Original Tools

Recon OS is a faithful port of seven standalone reconciliation tools (5 HTML/JS
utilities, one VBA macro + workbook, one Streamlit script) into one platform.
"Faithful" means the *business logic* — every rule, formula, and edge case —
was ported as-is, deliberately, even where it looks inconsistent or overly
clever. This document is the single place that lists every place the ported
behavior differs from a literal one-to-one copy, and why, so a differing
number between an original tool's output and Recon OS's output is either
traceable to an entry below or is a genuine bug to report.

Each module's own source file carries the same notes inline, closer to the
code they describe (`app/recon/modules/*.py`, `app/recon/utils/currency.py`).
This document exists as the one-stop index.

## Preserved quirks (intentional, not "fixed")

These are cases where the original tool's behavior is arguably inconsistent
or surprising, but changing it would silently change reconciliation output —
so it was kept exactly as observed, not "cleaned up."

- **NFS — two settlement totals.** The original computes both `finalAmt`
  (NTSL's own stated "Final Settlement Amount") and `settTot` (independently
  recomputed from ATM/BI/Micro/Switch/Dispute formulas). The on-screen
  MATCHED/PENDING/EXCESS/DEFICIT status compares `finalAmt` against the bank
  amount; the *exported Excel*'s live formula columns compare `settTot`
  instead. Recon OS keeps both numbers and reproduces both behaviors exactly.
  (`app/recon/modules/nfs.py`)
- **NFS — cycle assignment asymmetry.** Cycle-from-filename
  (`NTSLERODDMMYY_NC`) is only trusted for HTML-formatted NTSL exports. A
  real/merged `.xlsx` workbook always falls back to per-date, block-order
  cycle numbering (C1, C2, ...) — even for a single-block file. Preserved via
  the `is_html` flag threaded through the block parser.
- **UPI — dispute cycles carry different rows.** DC1/DC2 (dispute)
  settlement cycles only ever contain adjustment-type remarks (Net Adjusted
  Amount, Penalty, GST on Penalty, TDS on GST) in the real NPCI export — a
  normal cycle's Transaction Amount/Switching Fee/Approved Fee rows are
  filtered out for DC1/DC2, matching the original tool's `is_dc` gate.
- **PG Recon (Ops/PayU/Cashfree) — first-match rule order.** The
  `DetermineAction` rule table preserves the VBA's exact sequential
  if/return order, including acknowledged-redundant rules and the fallback.
  Re-ordering or de-duplicating it would silently change which action wins
  for status triples that satisfy multiple rules.
- **FASTag — two-pass bank matching with narrative-mismatch reclassification.**
  A second pass reclassifies amount-matched-but-narrative-mismatched rows,
  exactly as the original two-pass logic did.

## Presentation-only changes (same data, different layout)

- **RuPay & NFS Excel exports.** The originals used bare spreadsheet-letter
  headers (A..BH) under a 3-row merged group header (e.g. "NPCI Assessment
  Fees" > "POS" > "Amount"), because the group label only made sense
  combined. Recon OS uses one descriptive column name per field instead
  (e.g. "NPCI Assess POS") — every field the original captured is still
  present; only the header presentation is flattened.

## Structural changes required by the platform shift

- **6F/6R Data Preparation — no local folder path.** The original Streamlit
  script took a server-local folder path (`st.text_input` of a Windows path)
  because it ran on an analyst's own machine. Recon OS runs server-side
  behind a browser client with no access to a local filesystem path, so the
  input model is direct multi-file upload instead. The file-type
  classification and every processing rule is unchanged — only how files
  arrive changed.
- **Financial rounding (`app/recon/utils/currency.py`).** Every module
  reproduces the source tools' JS `Math.round(x*100)/100` semantics exactly
  — round-half-**toward-positive-infinity** for every input, including
  negative numbers (`Math.round(-0.5) === 0`, not `-1`). Python's built-in
  `round()` uses banker's rounding and would silently disagree on `.5` ties,
  so `_js_round()` reproduces the JS behavior via `math.floor(x + 0.5)`
  (mirrored for negatives) instead.

## Bugs fixed during the port (not preserved)

These were genuine defects in the original source, fixed rather than
carried forward, because the "mandatory parity" requirement is about
reproducing intended reconciliation behavior, not literal bugs.

- **Bank vs Add Money VBA macro** (`Bank_vs_Add_Money_Auto_Reconciliation_Utility_v1_17042026.bas`,
  fixed before the Python port):
  - An early `Exit Sub` on sheet-validation failure skipped the
    `Application.ScreenUpdating = True` / `Calculation = xlCalculationAutomatic`
    cleanup on the error path, leaving Excel's UI updating disabled if a run
    failed validation. Fixed with a `GoTo CleanUp` / `CleanUp:` label pattern
    so cleanup always runs.
  - `IIf()`'s eager evaluation of both branches meant `CDbl()` on an empty
    string could throw a type-mismatch error that `On Error Resume Next`
    silently swallowed, corrupting downstream totals with no visible error.
    Fixed with explicit `If/Then/Else` in the three affected spots.
  - A color constant (`CLR_NOTBANK_FNT`) was defined with the wrong value
    and was unused anyway (call sites hardcoded the correct RGB inline).
    Fixed the constant and wired up both usages to reference it, rather than
    leaving a dead/wrong constant in the code.

## What has NOT been validated against real production files

Every module above was validated against **synthetic fixtures** built to
match the documented row/column shapes, plus (for PG Recon specifically) the
real 15-row sample data embedded in the original `.xlsm` workbook. **NFS,
UPI, RuPay, and FASTag have not been run against real NPCI NTSL/DSR exports
or real bank statements.** The parsing logic, column detection, and cycle
assignment are all faithful to the documented format — but real exports can
carry formatting quirks (extra header rows, locale-specific number
formatting, merged cells, trailing whitespace in narratives) that synthetic
fixtures won't surface. Treat any NFS/UPI/RuPay/FASTag output as
provisional until validated against a real file set from production.

## Platform-level deviations (not module logic)

- **No mandatory login.** The original tools ran as local HTML files with no
  auth at all. Recon OS defaults to `AUTH_REQUIRED=false` (a shared "local"
  system user, matching that same no-login experience) rather than forcing
  a login screen — JWT/API-key auth exists and can be turned on via config
  for shared/exposed deployments, but it's opt-in, not the default.
- **API-key hashing uses SHA-256, not bcrypt.** Human passwords are hashed
  with bcrypt (slow, appropriate against offline guessing of low-entropy
  passwords). API keys are high-entropy random tokens generated by the
  server, not user-chosen — a fast salted hash is the standard, appropriate
  choice there; there's no guessing risk a slow hash would meaningfully
  defend against.
