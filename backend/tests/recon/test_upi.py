from app.recon.base import RunContext, UploadedFile
from app.recon.registry import get_module


def _run(make_xlsx):
    ntsl_rows = [
        [None], [None],
        ["Report as on 01-04-2026 (3C 10:00:00)"],
        [None],
        ["Description", "No. of Txns", "Debit", "Credit"],
        ["Transaction Amount", 10, 0, 1000.0],
        ["Switching Fee", 10, 5.0, 0],
        ["Switching Fee Gst", 10, 0.9, 0],
        ["Approved Fee", 10, 2.0, 0],
    ]
    ntsl_bytes = make_xlsx(ntsl_rows)
    bank_bytes = make_xlsx(
        [["Narrative", "c1", "c2", "c3", "Debit", "Credit"], ["Eroute UPI Setl 3C 010426", "", "", "", 0, 992.1]]
    )

    mod = get_module("upi")
    ctx = RunContext(
        run_id="test",
        files=[
            UploadedFile(slot="ntsl", filename="UPI_NTSLERT010426_3C.xlsx", content=ntsl_bytes, size_bytes=1),
            UploadedFile(slot="bank", filename="bank.xlsx", content=bank_bytes, size_bytes=1),
        ],
    )
    parsed = mod.parse(ctx)
    findings = mod.validate(parsed, ctx)
    return mod, ctx, parsed, findings


def test_remarks_classification(make_xlsx):
    _, _, parsed, _ = _run(make_xlsx)
    remarks = {r["desc"]: r["remarks"] for r in parsed.data["all_rows"]}
    assert remarks["Transaction Amount"] == "Transaction Amount"
    assert remarks["Switching Fee Gst"] == "Switching Fee Gst"
    assert remarks["Switching Fee"] == "Switching Fee"
    assert remarks["Approved Fee"] == "Approved Fee"


def test_pass2_grand_total_cross_check_passes(make_xlsx):
    _, _, parsed, findings = _run(make_xlsx)
    check = next(f for f in findings if f.check == "Grand total cross-check")
    assert check.level == "ok"


def test_bank_narrative_pattern1_matches_and_reconciles(make_xlsx):
    mod, ctx, parsed, findings = _run(make_xlsx)
    assert not any(f.level == "err" for f in findings)
    output = mod.reconcile(parsed, ctx, findings)
    row = output.raw["bank_rows"][0]
    assert row["Match Status"] == "Matched"
    assert row["NTSL Net"] == 992.1
    assert row["Difference"] == 0.0


def test_pass3_findings_all_ok(make_xlsx):
    mod, ctx, parsed, findings = _run(make_xlsx)
    output = mod.reconcile(parsed, ctx, findings)
    assert all(f.level == "ok" for f in output.findings)


def test_build_report_produces_valid_workbook(make_xlsx):
    mod, ctx, parsed, findings = _run(make_xlsx)
    output = mod.reconcile(parsed, ctx, findings)
    report = mod.build_report(output, ctx)
    assert report[:2] == b"PK"
