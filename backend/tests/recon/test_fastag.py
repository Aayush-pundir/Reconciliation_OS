from app.recon.base import RunContext, UploadedFile
from app.recon.registry import get_module


def _dsr_rows(day: str, gst: float, svc_total: float, net: float, toll_amt: float = 100.0, toll_cnt: int = 5):
    rows = [["Settlement Date"] + [None] * 29, [day] + [None] * 29]
    r = [None] * 30
    r[8], r[9], r[10], r[12] = "DEBIT", "TOLL", toll_cnt, toll_amt
    rows.append(r)
    r2 = [None] * 30
    r2[5], r2[18] = "INWARD GST", gst
    rows.append(r2)
    r3 = [None] * 30
    r3[1], r3[4], r3[18], r3[27] = "Total", "Total", svc_total, net
    rows.append(r3)
    return rows


def _run(make_xlsx):
    dsr1 = _dsr_rows("01-04-2026", gst=18.0, svc_total=118.0, net=218.0)
    dsr2 = _dsr_rows("01-04-2026", gst=9.0, svc_total=59.0, net=159.0)
    dsr3 = _dsr_rows("02-04-2026", gst=5.0, svc_total=25.0, net=125.0)  # last date -> Pending if unmatched

    # Bank columns: [PaymentDate(0), Narrative(1), c2, c3, c4, Debit(5)] - matches source's row[5] debit index.
    bank_rows = [
        ["Payment Date", "Narrative", "c2", "c3", "c4", "Debit"],
        ["02-04-2026", "XX_002026040101", "", "", "", 218.0],  # exact match: date01 cycle1
        ["03-04-2026", "XX_002026040502", "", "", "", 159.0],  # wrong date(05), right cycle(2), right amount -> reclass
    ]

    mod = get_module("fastag")
    ctx = RunContext(
        run_id="test",
        files=[
            UploadedFile(slot="dsr", filename="DSR_01.xlsx", content=make_xlsx(dsr1), size_bytes=1),
            UploadedFile(slot="dsr", filename="DSR_02.xlsx", content=make_xlsx(dsr2), size_bytes=1),
            UploadedFile(slot="dsr", filename="DSR_03.xlsx", content=make_xlsx(dsr3), size_bytes=1),
            UploadedFile(slot="bank", filename="bank.xlsx", content=make_xlsx(bank_rows), size_bytes=1),
        ],
    )
    parsed = mod.parse(ctx)
    findings = mod.validate(parsed, ctx)
    assert not any(f.level == "err" for f in findings)
    return mod.reconcile(parsed, ctx, findings)


def test_exact_match(make_xlsx):
    output = _run(make_xlsx)
    rows = {(r["DSR Date"], r["Cycle"]): r for r in output.raw["rows"]}
    assert rows[("01-04-2026", 1)]["Status"] == "Matched"
    assert rows[("01-04-2026", 1)]["Bank Debit"] == 218.0


def test_narrative_mismatch_reclassification(make_xlsx):
    output = _run(make_xlsx)
    rows = {(r["DSR Date"], r["Cycle"]): r for r in output.raw["rows"]}
    assert rows[("01-04-2026", 2)]["Status"] == "Matched – Narrative Mismatch*"


def test_last_date_unmatched_is_pending(make_xlsx):
    output = _run(make_xlsx)
    rows = {(r["DSR Date"], r["Cycle"]): r for r in output.raw["rows"]}
    assert rows[("02-04-2026", 1)]["Status"] == "Pending – Next Month Debit"


def test_build_report_produces_valid_workbook(make_xlsx):
    mod = get_module("fastag")
    output = _run(make_xlsx)
    ctx = RunContext(run_id="test")
    report = mod.build_report(output, ctx)
    assert report[:2] == b"PK"
