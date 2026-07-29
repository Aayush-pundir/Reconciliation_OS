"""RuPay Recon — faithful port of Rupay_Recon_Utility_v4_1 (DSR summary
files + bank statement, BIN/channel bucketing, triple validation). See
PRD §7.2.

Column naming note: the original tool's Excel output used bare
spreadsheet-column-letter headers (A..BH) under a 3-row merged group
header, because the group label ("NPCI Assessment Fees" > "POS" >
"Amount") only made sense combined. Recon OS uses single descriptive
column names instead (e.g. "NPCI Assess POS") carrying the same
information in one row - every field the original captured is still
present; only the header presentation is flattened for a cleaner UI.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from pydantic import Field

from app.recon.base import (
    InputSlot,
    OptionsBase,
    ParsedData,
    ReconModule,
    ReconOutput,
    ReportSheet,
    RunContext,
    StatCard,
    ValidationFinding,
)
from app.recon.registry import register
from app.recon.utils.currency import round2, to_float
from app.recon.utils.excel_read import read_rows
from app.recon.utils.excel_write import bold_font, freeze, set_cell, set_column_widths, solid_fill, write_row
from openpyxl import Workbook

DSR_FILENAME_RE = re.compile(r"ISSUER_(\d{4})-(\d{2})-(\d{2})-(\d)", re.IGNORECASE)
BANK_NARRATIVE_RE = re.compile(r"_00(\d{4})(\d{2})(\d{2})(\d{2})$")
ECOM_GC_BIN = 818014
PRESENTMENT_CYCLES = {"Presentment (With Auth)", "Offline Presentment(Without Auth)"}
NO_FEE_TYPES = {"Balance Update"}


def _get(row: list[Any], idx: int) -> Any:
    return row[idx] if idx < len(row) else None


def _new_dsr_accumulator() -> dict[str, Any]:
    return {
        "pos_count": 0, "pos_amt": 0.0, "ecom_count": 0, "ecom_amt": 0.0,
        "pos_gc_count": 0, "pos_gc_amt": 0.0, "ecom_gc_count": 0, "ecom_gc_amt": 0.0,
        "cash_pos_count": 0, "cash_pos_amt": 0.0,
        "npci_assess_pos": 0.0, "npci_assess_ecom": 0.0, "npci_assess_pos_gc": 0.0,
        "npci_assess_ecom_gc": 0.0, "npci_assess_cash": 0.0,
        "npci_proc_ecom": 0.0, "npci_proc_pos": 0.0,
        "int_income_cash": 0.0, "int_income_pos": 0.0, "int_income_ecom": 0.0,
        "int_income_pos_gc": 0.0, "int_income_ecom_gc": 0.0,
        "refund_pos": 0.0, "refund_ecom": 0.0, "qsparc_settled": 0.0,
        "chargeback_pos": 0.0, "chargeback_ecom": 0.0, "repres_pos": 0.0, "repres_ecom": 0.0,
        "dms_open_pos_cnt": 0, "dms_open_pos_amt": 0.0, "dms_open_ecom_cnt": 0, "dms_open_ecom_amt": 0.0,
        "open_npci_proc_ecom": 0.0, "open_npci_proc_pos": 0.0,
        "gst": 0.0, "final_net": 0.0,
    }


def parse_dsr(rows: list[list[Any]]) -> dict[str, Any]:
    r = _new_dsr_accumulator()
    c_bin: Any = None
    c_status: Any = None
    c_cycle: Any = None

    for raw_row in rows:
        if not raw_row or len(raw_row) < 10:
            continue
        row = list(raw_row) + [None] * max(0, 30 - len(raw_row))
        if all(v is None for v in row):
            continue

        if row[4] is not None and row[4] not in ("Total", "Acq ID / ISS Bin"):
            c_bin = row[4]
        if row[6] is not None and row[6] != "Status(Approved/Declined)":
            c_status = row[6]
        if row[7] is not None and row[7] != "Transaction Cycle":
            c_cycle = row[7]

        ch = row[9]
        cnt = to_float(row[10])
        txn_cr = to_float(row[13])
        set_dr = to_float(row[15])
        set_cr = to_float(row[16])
        int_cr = to_float(row[18])
        oth_dr = to_float(row[23])
        tt = row[8]
        f_cr = to_float(row[27])

        if row[1] == "Total" and row[2] == "Total" and row[3] == "Total" and row[4] == "Total" and row[5] == "Total":
            r["final_net"] = to_float(row[29])
        if row[5] == "INWARD GST":
            r["gst"] = to_float(row[25])

        bin_val = to_float(c_bin)
        if bin_val == ECOM_GC_BIN:
            if c_cycle in PRESENTMENT_CYCLES and tt == "Purchase" and c_status != "D":
                if ch == "ECOM" and set_dr > 0:
                    r["ecom_gc_count"] += cnt
                    r["ecom_gc_amt"] += set_dr
                    r["int_income_ecom_gc"] += int_cr
                    r["npci_assess_ecom_gc"] += oth_dr
                elif ch == "POS" and set_dr > 0:
                    r["pos_gc_count"] += cnt
                    r["pos_gc_amt"] += set_dr
                    r["int_income_pos_gc"] += int_cr
                    r["npci_assess_pos_gc"] += oth_dr
            if c_cycle == "Refund":
                if ch == "ECOM":
                    r["refund_ecom"] += set_cr if set_cr > 0 else txn_cr
                elif ch == "POS":
                    r["refund_pos"] += set_cr if set_cr > 0 else txn_cr

        if c_cycle in ("Chargeback Raise", "Chargeback Acceptance"):
            amt = max(set_cr, f_cr)
            if ch == "POS" and amt > 0:
                r["chargeback_pos"] += amt
            if ch == "ECOM" and amt > 0:
                r["chargeback_ecom"] += amt
        if c_cycle == "Re-Presentment Raise":
            if ch == "POS" and set_dr > 0:
                r["repres_pos"] += set_dr
            if ch == "ECOM" and set_dr > 0:
                r["repres_ecom"] += set_dr
        if c_cycle == "NPCI Fee Collection" and ch == "POS" and oth_dr > 0:
            r["cash_pos_count"] += cnt
            r["cash_pos_amt"] += oth_dr

        if bin_val != ECOM_GC_BIN:
            if c_cycle in PRESENTMENT_CYCLES and tt == "Purchase" and c_status != "D":
                if ch == "POS" and set_dr > 0:
                    r["pos_count"] += cnt
                    r["pos_amt"] += set_dr
                    r["int_income_pos"] += int_cr
                    r["npci_assess_pos"] += oth_dr
                elif ch == "ECOM" and set_dr > 0:
                    r["ecom_count"] += cnt
                    r["ecom_amt"] += set_dr
                    r["int_income_ecom"] += int_cr
                    r["npci_assess_ecom"] += oth_dr
            if tt == "qSPARC Money Load through Cash" and set_cr > 0:
                r["qsparc_settled"] += set_cr
            if c_cycle == "Refund":
                if ch == "ECOM":
                    r["refund_ecom"] += set_cr if set_cr > 0 else txn_cr
                elif ch == "POS":
                    r["refund_pos"] += set_cr if set_cr > 0 else txn_cr

        if c_cycle == "DMS Auth Transaction" and c_status == "A" and tt is not None:
            is_qsparc = "qSPARC" in str(tt) or "qSparc" in str(tt)
            if tt not in NO_FEE_TYPES and not is_qsparc and set_cr == 0 and oth_dr > 0:
                if ch == "ECOM":
                    r["npci_proc_ecom"] += oth_dr
                    if bin_val != ECOM_GC_BIN:
                        r["dms_open_ecom_cnt"] += cnt
                        r["dms_open_ecom_amt"] += to_float(row[12])
                        r["open_npci_proc_ecom"] += oth_dr
                elif ch == "POS":
                    r["npci_proc_pos"] += oth_dr
                    if bin_val != ECOM_GC_BIN:
                        r["dms_open_pos_cnt"] += cnt
                        r["dms_open_pos_amt"] += to_float(row[12])
                        r["open_npci_proc_pos"] += oth_dr

    total_assess = r["npci_assess_pos"] + r["npci_assess_ecom"] + r["npci_assess_pos_gc"] + r["npci_assess_ecom_gc"] + r["npci_assess_cash"]
    total_proc = r["npci_proc_ecom"] + r["npci_proc_pos"]
    r["gross"] = round2(
        -(r["pos_amt"] + r["pos_gc_amt"] + r["ecom_amt"] + r["ecom_gc_amt"] + r["cash_pos_amt"])
        + r["refund_pos"] + r["refund_ecom"] + r["qsparc_settled"]
        - total_assess - total_proc - r["int_income_cash"]
        + r["int_income_pos"] + r["int_income_ecom"] + r["int_income_pos_gc"] + r["int_income_ecom_gc"]
        + r["chargeback_pos"] + r["chargeback_ecom"] - r["repres_pos"] - r["repres_ecom"]
    )
    r["net_settlement"] = round2(r["final_net"])
    return r


def parse_bank(rows: list[list[Any]]) -> dict[str, float]:
    if not rows:
        return {}
    header = [str(v or "").lower() for v in rows[0]]
    idx_narr = next((i for i, h in enumerate(header) if "narr" in h or "desc" in h), 2)
    idx_credit = next((i for i, h in enumerate(header) if "credit" in h), 7)
    idx_debit = next((i for i, h in enumerate(header) if "debit" in h), 6)

    out: dict[str, float] = {}
    for row in rows[1:]:
        if not row:
            continue
        narrative = str(_get(row, idx_narr) or "")
        if "Rev_" in narrative:
            continue
        m = BANK_NARRATIVE_RE.search(narrative)
        if not m:
            continue
        yr, mo, dd, cc = m.groups()
        key = f"{yr}-{mo}-{dd}-C{int(cc)}"
        out[key] = out.get(key, 0.0) + to_float(_get(row, idx_credit)) - to_float(_get(row, idx_debit))
    return out


DETAIL_COLUMNS = [
    "Date", "Cycle",
    "POS Count", "POS Amount", "ECOM Count", "ECOM Amount", "Cash@POS Count", "Cash@POS Amount",
    "POS-GC Count", "POS-GC Amount", "ECOM-GC Count", "ECOM-GC Amount",
    "NPCI Assess POS", "NPCI Assess ECOM", "NPCI Assess Cash@POS",
    "NPCI Proc ECOM", "NPCI Proc POS",
    "Interchange Income Cash@POS", "Interchange Income POS", "Interchange Income ECOM",
    "Interchange Income POS-GC", "Interchange Income ECOM-GC",
    "Refund POS", "Refund ECOM", "qSPARC Load Cash",
    "Chargeback POS", "Chargeback ECOM", "Re-Presentment POS", "Re-Presentment ECOM",
    "Gross Total", "GST", "Net Settlement", "Bank Settled Amount", "Bank Settlement Date", "Difference",
    "DMS Open POS Count", "DMS Open POS Amount", "DMS Open ECOM Count", "DMS Open ECOM Amount",
    "Open NPCI Proc ECOM", "Open NPCI Proc POS",
]


class RupayOptions(OptionsBase):
    diff_tolerance: float = Field(default=1.0, description="₹ tolerance for zero-diff classification")


class RupayModule(ReconModule):
    key = "rupay"
    display_name = "RuPay Recon"
    description = "Reconciles RuPay DSR summary files (POS/ECOM/Gift Card) against a bank statement, with triple validation."
    version = "1.0.0"
    input_slots = [
        InputSlot(
            key="dsr", label="DSR Summary Files", accept=[".xls", ".xlsx"], multiple=True, required=True,
            filename_pattern=r"ISSUER_\d{4}-\d{2}-\d{2}-\d",
            help_text="Filename must contain ISSUER_YYYY-MM-DD-C",
        ),
        InputSlot(key="bank", label="Bank Statement", accept=[".xlsx", ".xls"], required=True),
    ]
    options_schema = RupayOptions

    def parse(self, ctx: RunContext) -> ParsedData:
        dsr_files = ctx.files_for("dsr")
        bank_file = ctx.files_for("bank")[0]

        dsr_data: dict[str, dict[str, Any]] = {}
        skipped: list[dict[str, str]] = []
        for f in dsr_files:
            m = DSR_FILENAME_RE.search(f.filename)
            if not m:
                skipped.append({"file": f.filename, "reason": "filename does not match ISSUER_YYYY-MM-DD-C"})
                continue
            key = f"{m.group(1)}-{m.group(2)}-{m.group(3)}-C{int(m.group(4))}"
            rows = read_rows(f.content, f.filename)
            dsr_data[key] = parse_dsr(rows)

        bank_rows = read_rows(bank_file.content, bank_file.filename)
        bank_map = parse_bank(bank_rows)

        ctx.info(f"Parsed {len(dsr_data)} DSR cycle(s), {len(skipped)} skipped, {len(bank_map)} bank cycle(s)")
        return ParsedData(data={"dsr_data": dsr_data, "bank_map": bank_map, "skipped": skipped, "file_count": len(dsr_files)})

    def validate(self, parsed: ParsedData, ctx: RunContext) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        dsr_data = parsed.data["dsr_data"]

        if not dsr_data:
            findings.append(ValidationFinding(pass_name="Input Integrity", check="DSR files", level="err", message="No valid DSR files parsed"))
            return findings

        v1_warn = v2_warn = v3_warn = 0
        for key, d in dsr_data.items():
            total_fees = (
                d["npci_assess_pos"] + d["npci_assess_ecom"] + d["npci_assess_pos_gc"] + d["npci_assess_ecom_gc"]
                + d["npci_assess_cash"] + d["npci_proc_ecom"] + d["npci_proc_pos"]
            )
            gst_check = round2(total_fees * 0.18)
            if abs(gst_check - d["gst"]) > 0.10:
                findings.append(
                    ValidationFinding(
                        pass_name="Triple Validation",
                        check=f"V1 — {key}",
                        level="warn",
                        message=f"fees×18%={gst_check:.2f} INWARD_GST={d['gst']:.2f}",
                    )
                )
                v1_warn += 1
            if abs(d["net_settlement"] - d["final_net"]) > 0.01:
                findings.append(
                    ValidationFinding(
                        pass_name="Triple Validation",
                        check=f"V2 — {key}",
                        level="warn",
                        message=f"net_settlement={d['net_settlement']:.2f} final_net={d['final_net']:.2f}",
                    )
                )
                v2_warn += 1
            settled = d["pos_amt"] + d["ecom_amt"] + d["qsparc_settled"]
            if d["final_net"] == 0 and settled > 0:
                findings.append(
                    ValidationFinding(
                        pass_name="Triple Validation",
                        check=f"V3 — {key}",
                        level="warn",
                        message=f"final_net=0 but settlements={settled:.2f}",
                    )
                )
                v3_warn += 1

        total_warn = v1_warn + v2_warn + v3_warn
        if total_warn == 0:
            findings.append(
                ValidationFinding(
                    pass_name="Triple Validation", check="Overall", level="ok",
                    message="ALL 3 checks PASSED for all cycles",
                )
            )
        else:
            findings.append(
                ValidationFinding(
                    pass_name="Triple Validation", check="Overall", level="warn",
                    message=f"{total_warn} warning(s) — review individual checks",
                )
            )
        return findings

    def reconcile(self, parsed: ParsedData, ctx: RunContext, findings: list[ValidationFinding]) -> ReconOutput:
        dsr_data: dict[str, dict[str, Any]] = parsed.data["dsr_data"]
        if not dsr_data:
            return ReconOutput(stats=[StatCard(label="Status", value="No valid DSR files", tone="bad")])

        options = RupayOptions(**ctx.options)
        bank_map: dict[str, float] = parsed.data["bank_map"]

        rows: list[dict[str, Any]] = []
        zero_diff = bad_diff = 0
        for key in sorted(dsr_data.keys()):
            d = dsr_data[key]
            m = re.match(r"^(\d{4})-(\d{2})-(\d{2})-C(\d+)$", key)
            year, month, day, cycle = m.groups()
            txn_date = date(int(year), int(month), int(day))
            settle_date = txn_date + timedelta(days=1)

            ab = round2(bank_map[key]) if key in bank_map else None
            if ab is None and d["final_net"] != 0:
                ab = round2(d["final_net"])
            gross = round2(d["gross"])
            gst_negative = round2(-d["gst"])
            net_settlement = round2(d["net_settlement"])

            diff_val = None
            if ab is not None:
                diff_val = round2(net_settlement - ab)
                if abs(diff_val) < options.diff_tolerance:
                    zero_diff += 1
                else:
                    bad_diff += 1

            rows.append(
                {
                    "Date": txn_date.isoformat(),
                    "Cycle": f"C{cycle}",
                    "POS Count": round(d["pos_count"]), "POS Amount": round2(d["pos_amt"]),
                    "ECOM Count": round(d["ecom_count"]), "ECOM Amount": round2(d["ecom_amt"]),
                    "Cash@POS Count": round(d["cash_pos_count"]), "Cash@POS Amount": round2(d["cash_pos_amt"]),
                    "POS-GC Count": round(d["pos_gc_count"]), "POS-GC Amount": round2(d["pos_gc_amt"]),
                    "ECOM-GC Count": round(d["ecom_gc_count"]), "ECOM-GC Amount": round2(d["ecom_gc_amt"]),
                    "NPCI Assess POS": round2(d["npci_assess_pos"] + d["npci_assess_pos_gc"]),
                    "NPCI Assess ECOM": round2(d["npci_assess_ecom"] + d["npci_assess_ecom_gc"]),
                    "NPCI Assess Cash@POS": round2(d["npci_assess_cash"]),
                    "NPCI Proc ECOM": round2(d["npci_proc_ecom"]), "NPCI Proc POS": round2(d["npci_proc_pos"]),
                    "Interchange Income Cash@POS": round2(d["int_income_cash"]),
                    "Interchange Income POS": round2(d["int_income_pos"]),
                    "Interchange Income ECOM": round2(d["int_income_ecom"]),
                    "Interchange Income POS-GC": round2(d["int_income_pos_gc"]),
                    "Interchange Income ECOM-GC": round2(d["int_income_ecom_gc"]),
                    "Refund POS": round2(d["refund_pos"]), "Refund ECOM": round2(d["refund_ecom"]),
                    "qSPARC Load Cash": round2(d["qsparc_settled"]),
                    "Chargeback POS": round2(d["chargeback_pos"]), "Chargeback ECOM": round2(d["chargeback_ecom"]),
                    "Re-Presentment POS": round2(d["repres_pos"]), "Re-Presentment ECOM": round2(d["repres_ecom"]),
                    "Gross Total": gross, "GST": gst_negative, "Net Settlement": net_settlement,
                    "Bank Settled Amount": ab, "Bank Settlement Date": settle_date.isoformat(),
                    "Difference": diff_val,
                    "DMS Open POS Count": round(d["dms_open_pos_cnt"]), "DMS Open POS Amount": round2(d["dms_open_pos_amt"]),
                    "DMS Open ECOM Count": round(d["dms_open_ecom_cnt"]), "DMS Open ECOM Amount": round2(d["dms_open_ecom_amt"]),
                    "Open NPCI Proc ECOM": round2(d["open_npci_proc_ecom"]), "Open NPCI Proc POS": round2(d["open_npci_proc_pos"]),
                }
            )

        matched = sum(1 for k in dsr_data if k in bank_map)
        unmatched = [k for k in dsr_data if k not in bank_map]

        stats = [
            StatCard(label="DSR Files", value=str(parsed.data["file_count"])),
            StatCard(label="Bank Entries", value=str(len(bank_map))),
            StatCard(label="Matched", value=str(matched), tone="good"),
            StatCard(label="Unmatched Cycles", value=str(len(unmatched)), tone="warn" if unmatched else "good"),
            StatCard(label="Zero-Diff Rows", value=str(zero_diff), tone="good"),
            StatCard(label=f"Diff > ₹{options.diff_tolerance:.0f} Rows", value=str(bad_diff), tone="bad" if bad_diff else "good"),
        ]

        exception_rows = [r for r in rows if r["Difference"] is None or abs(r["Difference"]) >= options.diff_tolerance]
        sheets = [
            ReportSheet(name="Rupay Control Sheet", kind="detail", columns=DETAIL_COLUMNS, rows=rows),
            ReportSheet(name="Exceptions", kind="exception", columns=DETAIL_COLUMNS, rows=exception_rows),
        ]
        return ReconOutput(stats=stats, sheets=sheets, findings=[], raw={"columns": DETAIL_COLUMNS, "rows": rows})

    def build_report(self, output: ReconOutput, ctx: RunContext) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = "Rupay Control Sheet"
        columns = output.raw["columns"]
        set_column_widths(ws, {1: 12, 2: 8} | {i: 15 for i in range(3, len(columns) + 1)})
        for i, name in enumerate(columns, start=1):
            set_cell(ws, 1, i, name, fill=solid_fill("FFBDD7EE"))
            bold_font(ws.cell(row=1, column=i))
        freeze(ws, "C2")

        row_idx = 2
        green = solid_fill("FFC6EFCE")
        red = solid_fill("FFFFC7CE")
        diff_col = columns.index("Difference") + 1
        for row in output.raw["rows"]:
            values = [row.get(c) for c in columns]
            write_row(ws, row_idx, values)
            diff_val = row.get("Difference")
            if diff_val is not None:
                ws.cell(row=row_idx, column=diff_col).fill = green if abs(diff_val) < 1 else red
            row_idx += 1

        data_end = row_idx - 1
        total_row = row_idx
        set_cell(ws, total_row, 2, "TOTAL", fill=solid_fill("FFD9E1F2"))
        bold_font(ws.cell(row=total_row, column=2))
        numeric_cols = [i for i, c in enumerate(columns, start=1) if "Count" not in c and c not in ("Date", "Cycle", "Bank Settlement Date", "Difference")]
        for col in numeric_cols:
            letter = ws.cell(row=1, column=col).column_letter
            set_cell(ws, total_row, col, f"=SUM({letter}2:{letter}{data_end})", fill=solid_fill("FFD9E1F2"))

        import io

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()


register(RupayModule())
