from app.recon.base import RunContext, UploadedFile
from app.recon.registry import get_module


def _run(make_xlsx):
    ntsl_rows = [
        ["Daily Settlement Statement as on 01/04/2026 (C1 10:00:00)"] + [None] * 5,
        ["Issuer WDL Transaction Amount", 10, 5000.0] + [None] * 3,
        ["Issuer WDL Approved Fee", 10, 190.0] + [None] * 3,
        ["Issuer WDL Transaction Amount (Micro-ATM)", None, 1000.0] + [None] * 3,
        ["Issuer WDLTransaction (Micro ATM)", "Rs. 100 and above", 3] + [None] * 3,
        ["Issuer BI Approved Fee", 4] + [None] * 4,
        ["Dispute Adjustments"] + [None] * 5,
        ["Adjustment Sub Totals", None, 50.0, 20.0] + [None] * 2,
        ["Summary for Micro"] + [None] * 5,
        ["Final Settlement Amount", 5321.50] + [None] * 4,
    ]
    ntsl_bytes = make_xlsx(ntsl_rows)
    bank_bytes = make_xlsx(
        [
            ["Payment date", "Narrative", "Eroute Remarks", "Debit"],
            ["02-04-2026", "NFS EROUTE TECH PVT LTD_002026040101", "NFS", 5321.50],
        ]
    )

    mod = get_module("nfs")
    ctx = RunContext(
        run_id="test",
        files=[
            UploadedFile(slot="ntsl", filename="NTSLERO010426_1C.xlsx", content=ntsl_bytes, size_bytes=1),
            UploadedFile(slot="bank", filename="bank.xlsx", content=bank_bytes, size_bytes=1),
        ],
    )
    parsed = mod.parse(ctx)
    findings = mod.validate(parsed, ctx)
    return mod, ctx, parsed, findings


def test_block_parsing_and_fee_formulas(make_xlsx):
    _, _, parsed, findings = _run(make_xlsx)
    assert not any(f.level == "err" for f in findings)
    block = parsed.data["blocks"][0]
    assert block["finalAmt"] == 5321.5
    assert block["atmFee"] == 190.0  # stated fee used (non-zero), not count*19 fallback
    assert block["atmFeeGST"] == round(190.0 * 0.18, 2)
    assert block["biTot"] == round(4 * 6 * 1.18, 2)


def test_bank_match_matched_status(make_xlsx):
    mod, ctx, parsed, findings = _run(make_xlsx)
    output = mod.reconcile(parsed, ctx, findings)
    row = output.raw["detail_rows"][0]
    assert row["Status"] == "MATCHED"
    assert row["NTSL Final Amount"] == 5321.5
    assert row["Bank Amount"] == 5321.5


def test_build_report_produces_valid_workbook(make_xlsx):
    mod, ctx, parsed, findings = _run(make_xlsx)
    output = mod.reconcile(parsed, ctx, findings)
    report = mod.build_report(output, ctx)
    assert report[:2] == b"PK"
