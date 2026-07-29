"""Manual load test (PRD fast-follow #18): 500-file UPI and 150-file RuPay
batches, timing parse()+validate()+reconcile() end to end. Not a pytest
test - this exercises volume/performance, not correctness (that's covered
by the per-module unit tests), and takes long enough that it doesn't
belong in the default CI-run suite.

Usage: cd backend && source .venv/bin/activate && python scripts/load_test.py
"""
from __future__ import annotations

import io
import time
from datetime import date, timedelta

from openpyxl import Workbook

from app.recon.base import RunContext, UploadedFile
from app.recon.registry import get_module


def _xlsx(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def load_test_upi(n_files: int = 500) -> None:
    from app.recon.modules.upi import CYCLE_ORDER

    ntsl_files: list[UploadedFile] = []
    bank_rows = [["Narrative", "c1", "c2", "c3", "Debit", "Credit"]]
    start = date(2025, 1, 1)

    for i in range(n_files):
        d = start + timedelta(days=i // len(CYCLE_ORDER))
        cycle = CYCLE_ORDER[i % len(CYCLE_ORDER)]
        ddmmyy = f"{d.day:02d}{d.month:02d}{d.strftime('%y')}"
        header = [
            [None], [None],
            [f"Report as on {d.day:02d}-{d.month:02d}-{d.year} ({cycle} 10:00:00)"],
            [None],
            ["Description", "No. of Txns", "Debit", "Credit"],
        ]
        if cycle in ("DC1", "DC2"):
            # Dispute cycles only carry adjustment-type rows in the real NPCI
            # export (see upi.py's `is_dc` gate) - a regular txn/fee row set
            # would be silently dropped, same as the real module does.
            ntsl_rows = header + [["Net Adjusted Amount", 1, 0, 992.1]]
        else:
            ntsl_rows = header + [
                ["Transaction Amount", 10, 0, 1000.0],
                ["Switching Fee", 10, 5.0, 0],
                ["Switching Fee Gst", 10, 0.9, 0],
                ["Approved Fee", 10, 2.0, 0],
            ]
        ntsl_files.append(
            UploadedFile(
                slot="ntsl", filename=f"UPI_NTSLERT{ddmmyy}_{cycle}.xlsx",
                content=_xlsx(ntsl_rows), size_bytes=1,
            )
        )
        bank_rows.append([f"Eroute UPI Setl {cycle} {ddmmyy}", "", "", "", 0, 992.1])

    bank_file = UploadedFile(slot="bank", filename="bank.xlsx", content=_xlsx(bank_rows), size_bytes=1)

    mod = get_module("upi")
    ctx = RunContext(run_id="loadtest-upi", files=[*ntsl_files, bank_file])

    t0 = time.perf_counter()
    parsed = mod.parse(ctx)
    t1 = time.perf_counter()
    findings = mod.validate(parsed, ctx)
    t2 = time.perf_counter()
    output = mod.reconcile(parsed, ctx, findings)
    t3 = time.perf_counter()
    report = mod.build_report(output, ctx)
    t4 = time.perf_counter()

    errs = [f for f in findings if f.level == "err"]
    statuses: dict[str, int] = {}
    for r in output.raw["bank_rows"]:
        statuses[r["Match Status"]] = statuses.get(r["Match Status"], 0) + 1
    print(f"UPI load test: {n_files} files")
    print(f"  parse:     {t1 - t0:6.2f}s")
    print(f"  validate:  {t2 - t1:6.2f}s")
    print(f"  reconcile: {t3 - t2:6.2f}s")
    print(f"  report:    {t4 - t3:6.2f}s  ({len(report):,} bytes)")
    print(f"  total:     {t4 - t0:6.2f}s")
    print(f"  parsed blocks: {len(parsed.data.get('all_rows', []))} rows, {len(errs)} error-level findings")
    print(f"  bank match status breakdown: {statuses}")
    print()

    assert not errs, f"expected 0 error-level findings, got {len(errs)}"
    assert statuses.get("Matched") == n_files, f"expected all {n_files} bank rows matched, got {statuses}"
    assert t4 - t0 < 30, f"UPI {n_files}-file batch took {t4 - t0:.1f}s, exceeds 30s budget"


def load_test_rupay(n_files: int = 150) -> None:
    def row30(overrides: dict[int, object]) -> list:
        r = [None] * 30
        for k, v in overrides.items():
            r[k] = v
        return r

    dsr_files: list[UploadedFile] = []
    bank_rows = [["Narrative", "Debit", "Credit"]]
    start = date(2025, 1, 1)

    for i in range(n_files):
        d = start + timedelta(days=i)
        cycle_digit = 1
        rows = [
            row30({4: 111111, 6: "A", 7: "Presentment (With Auth)", 8: "Purchase", 9: "POS", 10: 2, 13: 0, 15: 100.0, 16: 0, 18: 1.0, 23: 2.0}),
            row30({5: "INWARD GST", 25: 18.0}),
        ]
        grand_total = [None] * 30
        grand_total[1] = grand_total[2] = grand_total[3] = grand_total[4] = grand_total[5] = "Total"
        grand_total[29] = 80.0
        rows.append(grand_total)
        dsr_files.append(
            UploadedFile(
                slot="dsr", filename=f"ISSUER_{d.isoformat()}-{cycle_digit}.xlsx",
                content=_xlsx(rows), size_bytes=1,
            )
        )
        bank_rows.append([f"PAYMENT_00{d.strftime('%Y%m%d')}01", 0, 80.0])

    bank_file = UploadedFile(slot="bank", filename="bank.xlsx", content=_xlsx(bank_rows), size_bytes=1)

    mod = get_module("rupay")
    ctx = RunContext(run_id="loadtest-rupay", files=[*dsr_files, bank_file])

    t0 = time.perf_counter()
    parsed = mod.parse(ctx)
    t1 = time.perf_counter()
    findings = mod.validate(parsed, ctx)
    t2 = time.perf_counter()
    output = mod.reconcile(parsed, ctx, findings)
    t3 = time.perf_counter()
    report = mod.build_report(output, ctx)
    t4 = time.perf_counter()

    errs = [f for f in findings if f.level == "err"]
    matched = sum(1 for r in output.raw["rows"] if r.get("Bank Settled Amount") is not None and abs(r.get("Difference") or 0) < 0.01)
    unmatched = len(output.raw["rows"]) - matched
    print(f"RuPay load test: {n_files} files")
    print(f"  parse:     {t1 - t0:6.2f}s")
    print(f"  validate:  {t2 - t1:6.2f}s")
    print(f"  reconcile: {t3 - t2:6.2f}s")
    print(f"  report:    {t4 - t3:6.2f}s  ({len(report):,} bytes)")
    print(f"  total:     {t4 - t0:6.2f}s")
    print(f"  dsr cycles parsed: {len(parsed.data.get('dsr_data', {}))}, {len(errs)} error-level findings")
    print(f"  matched: {matched}, unmatched: {unmatched}")
    print()

    assert not errs, f"expected 0 error-level findings, got {len(errs)}"
    assert unmatched == 0, f"expected all {n_files} DSR cycles matched, got {unmatched} unmatched"
    assert t4 - t0 < 30, f"RuPay {n_files}-file batch took {t4 - t0:.1f}s, exceeds 30s budget"


if __name__ == "__main__":
    load_test_upi(500)
    load_test_rupay(150)
    print("LOAD TEST PASSED")
