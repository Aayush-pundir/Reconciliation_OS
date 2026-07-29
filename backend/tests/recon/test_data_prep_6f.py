from app.recon.base import RunContext, UploadedFile
from app.recon.registry import get_module


def _run(make_xlsx):
    normal_rows = [
        ["Status", "TransactionCategory", "TransactionDate", "TransactionType", "Amount"],
        ["Completed", "Add Money", "01-04-2026", "Credit", 100.0],
        ["Completed", "Reversal", "01-04-2026", "Credit", 50.0],  # excluded: reversal token
        ["Failed", "Add Money", "01-04-2026", "Debit", 30.0],  # excluded: not completed
        ["Completed", "Add Money", "01-04-2026", "Debit", 20.0],
    ]
    gift_rows = [
        ["Status", "TransactionCategory", "TransactionDate", "TransactionType", "Amount"],
        ["Completed", "Gift Load", "01-04-2026", "Credit", 40.0],
    ]
    ncmc_rows = [["SETTLEMENTDATE", "SETTLEMENTAMT", "TRXN_TYPE"], ["20260401", 15.0, "Credit"]]

    mod = get_module("data_prep_6f")
    ctx = RunContext(
        run_id="test",
        files=[
            UploadedFile(slot="files", filename="BigFile_Normal.xlsx", content=make_xlsx(normal_rows), size_bytes=11 * 1024 * 1024),
            UploadedFile(slot="files", filename="GIFT_export.xlsx", content=make_xlsx(gift_rows), size_bytes=1000),
            UploadedFile(slot="files", filename="NCMC_export.xlsx", content=make_xlsx(ncmc_rows), size_bytes=1000),
            UploadedFile(slot="files", filename="tiny_unknown.xlsx", content=make_xlsx(normal_rows), size_bytes=1000),
        ],
    )
    parsed = mod.parse(ctx)
    findings = mod.validate(parsed, ctx)
    return mod, ctx, parsed, findings


def test_unknown_small_file_skipped(make_xlsx):
    _, _, parsed, _ = _run(make_xlsx)
    reasons = {s["file"]: s["reason"] for s in parsed.data["skipped"]}
    assert "tiny_unknown.xlsx" in reasons


def test_reversal_and_non_completed_rows_excluded(make_xlsx):
    mod, ctx, parsed, findings = _run(make_xlsx)
    output = mod.reconcile(parsed, ctx, findings)
    row = output.raw["rows"][0]
    assert row["Credit-Normal"] == 100.0  # not 150 (reversal excluded)
    assert row["Debit-Normal"] == 20.0  # not 50 (failed row excluded)


def test_gift_and_ncmc_aggregated_separately(make_xlsx):
    mod, ctx, parsed, findings = _run(make_xlsx)
    output = mod.reconcile(parsed, ctx, findings)
    row = output.raw["rows"][0]
    assert row["Credit-Gifted"] == 40.0
    assert row["Credit-NCMC"] == 15.0


def test_build_report_produces_valid_workbook(make_xlsx):
    mod, ctx, parsed, findings = _run(make_xlsx)
    output = mod.reconcile(parsed, ctx, findings)
    report = mod.build_report(output, ctx)
    assert report[:2] == b"PK"
