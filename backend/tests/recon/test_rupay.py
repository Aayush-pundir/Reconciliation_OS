from app.recon.base import RunContext, UploadedFile
from app.recon.registry import get_module


def _row30(overrides: dict[int, object]) -> list:
    r = [None] * 30
    for k, v in overrides.items():
        r[k] = v
    return r


def _run(make_xlsx):
    rows = [
        _row30({4: 111111, 6: "A", 7: "Presentment (With Auth)", 8: "Purchase", 9: "POS", 10: 2, 13: 0, 15: 100.0, 16: 0, 18: 1.0, 23: 2.0}),
        _row30({5: "INWARD GST", 25: 18.0}),
    ]
    grand_total = [None] * 30
    grand_total[1] = grand_total[2] = grand_total[3] = grand_total[4] = grand_total[5] = "Total"
    grand_total[29] = 80.0
    rows.append(grand_total)

    dsr_bytes = make_xlsx(rows)
    bank_bytes = make_xlsx([["Narrative", "Debit", "Credit"], ["PAYMENT_002026040101", 0, 80.0]])

    mod = get_module("rupay")
    ctx = RunContext(
        run_id="test",
        files=[
            UploadedFile(slot="dsr", filename="ISSUER_2026-04-01-1.xlsx", content=dsr_bytes, size_bytes=1),
            UploadedFile(slot="bank", filename="bank.xlsx", content=bank_bytes, size_bytes=1),
        ],
    )
    parsed = mod.parse(ctx)
    findings = mod.validate(parsed, ctx)
    return mod, ctx, parsed, findings


def test_dsr_bin_channel_bucketing(make_xlsx):
    _, _, parsed, _ = _run(make_xlsx)
    d = parsed.data["dsr_data"]["2026-04-01-C1"]
    assert d["pos_count"] == 2.0
    assert d["pos_amt"] == 100.0
    assert d["npci_assess_pos"] == 2.0
    assert d["gst"] == 18.0
    assert d["final_net"] == 80.0


def test_bank_match_and_zero_diff(make_xlsx):
    mod, ctx, parsed, findings = _run(make_xlsx)
    output = mod.reconcile(parsed, ctx, findings)
    row = output.raw["rows"][0]
    assert row["Bank Settled Amount"] == 80.0
    assert row["Difference"] == 0.0


def test_triple_validation_v1_flags_fee_gst_mismatch(make_xlsx):
    # total_fees(=2.0) * 18% = 0.36, but INWARD_GST states 18.0 -> V1 should warn.
    _, _, parsed, findings = _run(make_xlsx)
    v1 = [f for f in findings if f.check.startswith("V1")]
    assert len(v1) == 1
    assert v1[0].level == "warn"


def test_build_report_produces_valid_workbook(make_xlsx):
    mod, ctx, parsed, findings = _run(make_xlsx)
    output = mod.reconcile(parsed, ctx, findings)
    report = mod.build_report(output, ctx)
    assert report[:2] == b"PK"
