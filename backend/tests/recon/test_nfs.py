from datetime import date

from app.recon.base import RunContext, UploadedFile
from app.recon.modules.nfs import (
    cycle_from_filename,
    date_from_filename,
    extract_date,
    parse_ntsl_rows,
)
from app.recon.registry import get_module


def _block_rows(
    as_on: str,
    final_amt: float,
    *,
    atm_count: int = 10,
    atm_amt: float = 5000.0,
    atm_fee: float = 190.0,
    micro_amt: float = 1000.0,
    micro_count: int = 3,
    bi_count: int = 4,
    dispute_debit: float = 50.0,
    dispute_credit: float = 20.0,
) -> list[list]:
    """One NTSL settlement block's raw rows, in source-tool order - the
    same shape `_run`'s single-block fixture used, factored out so multiple
    blocks can be concatenated into one "merged workbook" file."""
    return [
        [f"Daily Settlement Statement as on {as_on}"] + [None] * 5,
        ["Issuer WDL Transaction Amount", atm_count, atm_amt] + [None] * 3,
        ["Issuer WDL Approved Fee", atm_count, atm_fee] + [None] * 3,
        ["Issuer WDL Transaction Amount (Micro-ATM)", None, micro_amt] + [None] * 3,
        ["Issuer WDLTransaction (Micro ATM)", "Rs. 100 and above", micro_count] + [None] * 3,
        ["Issuer BI Approved Fee", bi_count] + [None] * 4,
        ["Dispute Adjustments"] + [None] * 5,
        ["Adjustment Sub Totals", None, dispute_debit, dispute_credit] + [None] * 2,
        ["Summary for Micro"] + [None] * 5,
        ["Final Settlement Amount", final_amt] + [None] * 4,
    ]


def _bank_rows(entries: list[tuple[str, str, float]]) -> list[list]:
    """entries: list of (payment_date, narrative, debit)."""
    rows = [["Payment date", "Narrative", "Eroute Remarks", "Debit"]]
    for pay_date, narrative, debit in entries:
        rows.append([pay_date, narrative, "NFS", debit])
    return rows


def _run(make_xlsx, ntsl_rows, bank_entries, ntsl_filename="NTSLERO010426_1C.xlsx", options: dict | None = None):
    ntsl_bytes = make_xlsx(ntsl_rows)
    bank_bytes = make_xlsx(_bank_rows(bank_entries))

    mod = get_module("nfs")
    ctx = RunContext(
        run_id="test",
        files=[
            UploadedFile(slot="ntsl", filename=ntsl_filename, content=ntsl_bytes, size_bytes=1),
            UploadedFile(slot="bank", filename="bank.xlsx", content=bank_bytes, size_bytes=1),
        ],
        options=options or {},
    )
    parsed = mod.parse(ctx)
    findings = mod.validate(parsed, ctx)
    return mod, ctx, parsed, findings


def test_block_parsing_and_fee_formulas(make_xlsx):
    _, _, parsed, findings = _run(
        make_xlsx,
        _block_rows("01/04/2026 (C1 10:00:00)", 5321.50),
        [("02-04-2026", "NFS EROUTE TECH PVT LTD_002026040101", 5321.50)],
    )
    assert not any(f.level == "err" for f in findings)
    block = parsed.data["blocks"][0]
    assert block["finalAmt"] == 5321.5
    assert block["atmFee"] == 190.0  # stated fee used (non-zero), not count*19 fallback
    assert block["atmFeeGST"] == round(190.0 * 0.18, 2)
    assert block["biTot"] == round(4 * 6 * 1.18, 2)


def test_bank_match_matched_status(make_xlsx):
    mod, ctx, parsed, findings = _run(
        make_xlsx,
        _block_rows("01/04/2026 (C1 10:00:00)", 5321.50),
        [("02-04-2026", "NFS EROUTE TECH PVT LTD_002026040101", 5321.50)],
    )
    output = mod.reconcile(parsed, ctx, findings)
    row = output.raw["detail_rows"][0]
    assert row["Status"] == "MATCHED"
    assert row["NTSL Final Amount"] == 5321.5
    assert row["Bank Amount"] == 5321.5


def test_build_report_produces_valid_workbook(make_xlsx):
    mod, ctx, parsed, findings = _run(
        make_xlsx,
        _block_rows("01/04/2026 (C1 10:00:00)", 5321.50),
        [("02-04-2026", "NFS EROUTE TECH PVT LTD_002026040101", 5321.50)],
    )
    output = mod.reconcile(parsed, ctx, findings)
    report = mod.build_report(output, ctx)
    assert report[:2] == b"PK"


# ── Merged-workbook / multi-block coverage ──────────────────────────────

def test_merged_workbook_two_blocks_same_date_get_sequential_cycles(make_xlsx):
    """A merged .xlsx (not HTML) has no cycle in its filename/content for
    either block - assign_cycles must fall back to per-date block-order
    numbering (C1, C2, ...), per the module's documented source-fidelity
    behavior for real/merged workbooks."""
    merged_rows = _block_rows("01/04/2026 (C1 10:00:00)", 1000.0, atm_count=5, atm_amt=2000.0) + _block_rows(
        "01/04/2026 (C2 14:00:00)", 2000.0, atm_count=8, atm_amt=3000.0
    )
    mod, ctx, parsed, findings = _run(
        make_xlsx,
        merged_rows,
        [
            ("02-04-2026", "NFS EROUTE TECH PVT LTD_002026040101", 1000.0),
            ("02-04-2026", "NFS EROUTE TECH PVT LTD_002026040102", 2000.0),
        ],
        ntsl_filename="merged_ntsl.xlsx",  # no _NC. cycle suffix -> not HTML, no cycleFromName
    )
    assert not any(f.level == "err" for f in findings)
    assert len(parsed.data["blocks"]) == 2

    output = mod.reconcile(parsed, ctx, findings)
    rows = sorted(output.raw["detail_rows"], key=lambda r: r["Cycle"])
    assert [r["Cycle"] for r in rows] == ["C1", "C2"]
    assert rows[0]["NTSL Final Amount"] == 1000.0
    assert rows[1]["NTSL Final Amount"] == 2000.0
    assert rows[0]["Status"] == "MATCHED"
    assert rows[1]["Status"] == "MATCHED"


def test_merged_workbook_blocks_across_different_dates(make_xlsx):
    merged_rows = _block_rows("01/04/2026 (C1 10:00:00)", 1000.0) + _block_rows("02/04/2026 (C1 10:00:00)", 1500.0)
    mod, ctx, parsed, findings = _run(
        make_xlsx,
        merged_rows,
        [
            ("02-04-2026", "NFS EROUTE TECH PVT LTD_002026040101", 1000.0),
            ("03-04-2026", "NFS EROUTE TECH PVT LTD_002026040201", 1500.0),
        ],
        ntsl_filename="merged_ntsl.xlsx",
    )
    assert len(parsed.data["blocks"]) == 2
    output = mod.reconcile(parsed, ctx, findings)
    rows = sorted(output.raw["detail_rows"], key=lambda r: r["Date"])
    assert rows[0]["Date"] == date(2026, 4, 1).isoformat()
    assert rows[1]["Date"] == date(2026, 4, 2).isoformat()
    # each date's first (only) block gets C1, independently
    assert rows[0]["Cycle"] == "C1"
    assert rows[1]["Cycle"] == "C1"


def test_html_export_uses_cycle_from_filename_not_block_order(make_xlsx):
    """The source tool only trusts the filename's cycle suffix
    (`NTSLERODDMMYY_NC.`) for HTML-formatted exports - verified here by
    feeding two single-block HTML files whose filenames carry different
    cycle numbers, and asserting those numbers win over order-based
    assignment (which would have given both files C1)."""

    def html_block(as_on: str, final_amt: float) -> bytes:
        rows = _block_rows(as_on, final_amt)
        trs = "".join("<tr>" + "".join(f"<td>{c if c is not None else ''}</td>" for c in row) + "</tr>" for row in rows)
        html = f"<html><body><table>{trs}</table></body></html>"
        return html.encode("utf-8")

    mod = get_module("nfs")
    ctx = RunContext(
        run_id="test",
        files=[
            UploadedFile(
                slot="ntsl", filename="NTSLERO010426_3C.xls",
                content=html_block("01/04/2026 (C3 10:00:00)", 4000.0), size_bytes=1,
            ),
            UploadedFile(
                slot="bank", filename="bank.xlsx",
                content=make_xlsx(_bank_rows([("02-04-2026", "NFS EROUTE TECH PVT LTD_002026040103", 4000.0)])),
                size_bytes=1,
            ),
        ],
    )
    parsed = mod.parse(ctx)
    findings = mod.validate(parsed, ctx)
    assert not any(f.level == "err" for f in findings)
    output = mod.reconcile(parsed, ctx, findings)
    row = output.raw["detail_rows"][0]
    assert row["Cycle"] == "C3"  # from filename, not block-order (which would be C1)
    assert row["Status"] == "MATCHED"


def test_block_missing_final_settlement_amount_is_dropped(make_xlsx):
    """A block that never hits a `Final Settlement Amount` row (truncated
    export, or a section NPCI omits for a zero-activity cycle) must not
    silently surface as a phantom row."""
    good = _block_rows("01/04/2026 (C1 10:00:00)", 1000.0)
    bad = [r for r in _block_rows("02/04/2026 (C1 10:00:00)", 999.0) if r[0] != "Final Settlement Amount"]
    mod, ctx, parsed, findings = _run(
        make_xlsx,
        good + bad,
        [("02-04-2026", "NFS EROUTE TECH PVT LTD_002026040101", 1000.0)],
        ntsl_filename="merged_ntsl.xlsx",
    )
    assert len(parsed.data["blocks"]) == 1
    assert parsed.data["blocks"][0]["finalAmt"] == 1000.0


def test_carry_over_bank_entries_outside_month_scope(make_xlsx):
    """Bank entries whose date falls in a month with no NTSL cycles (e.g.
    a stray settlement debit from an adjacent month) must land in the
    Carry Over sheet, not be silently matched or dropped."""
    mod, ctx, parsed, findings = _run(
        make_xlsx,
        _block_rows("15/04/2026 (C1 10:00:00)", 1000.0),
        [
            ("16-04-2026", "NFS EROUTE TECH PVT LTD_002026041501", 1000.0),
            ("03-05-2026", "NFS EROUTE TECH PVT LTD_002026050101", 777.0),  # different month, no matching NTSL cycle
        ],
        options={"month": "2026-04"},
    )
    output = mod.reconcile(parsed, ctx, findings)
    assert len(output.raw["detail_rows"]) == 1
    assert output.raw["detail_rows"][0]["Status"] == "MATCHED"
    assert len(output.raw["carry_rows"]) == 1
    assert output.raw["carry_rows"][0]["Bank Debit"] == 777.0
    carry_sheet = next(s for s in output.sheets if s.name == "Carry Over")
    assert len(carry_sheet.rows) == 1


# ── extract_date / filename-pattern unit coverage ───────────────────────

def test_extract_date_slash_format():
    assert extract_date("Daily Settlement Statement as on 05/04/2026 (C1)", []) == date(2026, 4, 5)


def test_extract_date_dash_format():
    assert extract_date("Daily Settlement Statement as on 05-04-2026 (C1)", []) == date(2026, 4, 5)


def test_extract_date_iso_format():
    assert extract_date("Daily Settlement Statement as on 2026-04-05 (C1)", []) == date(2026, 4, 5)


def test_extract_date_month_abbreviation_format():
    assert extract_date("Daily Settlement Statement as on 5 Apr 2026 (C1)", []) == date(2026, 4, 5)


def test_extract_date_falls_back_to_datetime_cell_in_row():
    from datetime import datetime

    row = [None, datetime(2026, 4, 5, 10, 0, 0), None]
    assert extract_date("Daily Settlement Statement (no as-on text)", row) == date(2026, 4, 5)


def test_extract_date_unparseable_returns_none():
    assert extract_date("Daily Settlement Statement as on not-a-date", []) is None


def test_cycle_from_filename_extracts_cycle_number():
    assert cycle_from_filename("NTSLERO010426_3C.xlsx") == "C3"
    assert cycle_from_filename("no_cycle_suffix.xlsx") is None


def test_date_from_filename_parses_ddmmyy():
    assert date_from_filename("NTSLERO010426_1C.xlsx") == date(2026, 4, 1)
    assert date_from_filename("unrelated_file.xlsx") is None


def test_parse_ntsl_rows_ignores_rows_before_first_block_header():
    """Stray preamble rows (report titles, blank rows) before the first
    'Daily Settlement Statement' header must not be misread as block data."""
    rows = [["Some Report Title"], [None] * 3] + _block_rows("01/04/2026 (C1 10:00:00)", 1234.0)
    blocks = parse_ntsl_rows(rows, "merged_ntsl.xlsx", is_html=False)
    assert len(blocks) == 1
    assert blocks[0]["finalAmt"] == 1234.0
