"""NFS Settlement Recon — faithful port of NFS_Recon_Tool_v5. See PRD §7.1.

Two source-fidelity notes worth documenting explicitly (both preserved
on purpose, not "fixed", per the mandatory-parity requirement):

1. The original tool computes TWO different "settlement total" figures
   per cycle: `finalAmt` (the NTSL's own stated "Final Settlement Amount")
   and `settTot` (independently recomputed from ATM/BI/Micro/Switch/Dispute
   fee formulas). The on-screen MATCHED/PENDING/EXCESS/DEFICIT status uses
   `finalAmt` vs. the bank amount; the *exported Excel*'s own live formula
   columns recompute `settTot` from raw counts/amounts and diff *that*
   against the bank amount. We keep both numbers and reproduce both
   behaviors: `status`/`diff` (persisted, shown on screen) are
   finalAmt-based; the Excel `build_report()` writes the same
   count/amount-driven live-formula chain the original workbook used.
2. Cycle-from-filename (`NTSLERODDMMYY_NC`) is only applied for
   HTML-formatted NTSL exports in the source tool - a real/merged
   .xlsx workbook always falls back to per-date block-order cycle
   assignment, even for a single-block file. Preserved via the
   `is_html` flag on the block parser below.

Column naming: like the RuPay module, the exported sheet uses descriptive
column names in a single header row instead of the original's 3-row
merged spreadsheet-letter header - same data, clearer presentation.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
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
from app.recon.utils.currency import round2, round4, to_float, to_int
from app.recon.utils.excel_read import read_rows, sniff_format
from app.recon.utils.excel_write import bold_font, freeze, set_cell, set_column_widths, solid_fill, write_row
from openpyxl import Workbook

MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


class NFSOptions(OptionsBase):
    threshold: float = Field(default=1.0, description="₹ tolerance for MATCHED status")
    month: str | None = Field(default=None, description="Optional YYYY-MM filter; blank = all loaded months")


def _get(row: list[Any], idx: int) -> Any:
    return row[idx] if row is not None and idx < len(row) else None


def fmt_d(d: date) -> str:
    return f"{d.day:02d}-{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.month-1]}-{d.year}"


def fmt_mo(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def cycle_from_filename(filename: str) -> str | None:
    m = re.search(r"_(\d+)C\.", filename, re.IGNORECASE)
    return f"C{int(m.group(1))}" if m else None


def date_from_filename(filename: str) -> date | None:
    m = re.search(r"NTSLERO(\d{2})(\d{2})(\d{2,4})_\d+C", filename, re.IGNORECASE)
    if not m:
        return None
    dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    year = yy if yy >= 100 else (2000 + yy if yy < 50 else 1900 + yy)
    try:
        return date(year, mm, dd)
    except ValueError:
        return None


def extract_date(text: str, row: list[Any]) -> date | None:
    patterns = [
        (r"as on\s+(\d{2})/(\d{2})/(\d{4})", lambda m: date(int(m[3]), int(m[2]), int(m[1]))),
        (r"as on\s+(\d{2})-(\d{2})-(\d{4})", lambda m: date(int(m[3]), int(m[2]), int(m[1]))),
        (r"as on\s+(\d{4})-(\d{2})-(\d{2})", lambda m: date(int(m[1]), int(m[2]), int(m[3]))),
    ]
    for pattern, build in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                return build(m)
            except ValueError:
                pass
    m = re.search(r"as on\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", text, re.IGNORECASE)
    if m:
        month = MONTH_ABBR.get(m.group(2).lower())
        if month:
            try:
                return date(int(m.group(3)), month, int(m.group(1)))
            except ValueError:
                pass
    for cell in row or []:
        if isinstance(cell, datetime):
            return cell.date()
        if isinstance(cell, date):
            return cell
    return None


def _build_block(cur: dict[str, Any]) -> dict[str, Any]:
    atm_fee = cur["atmFee"] if (cur["atmFee"] is not None and cur["atmFee"] != 0) else cur["atmCount"] * 19
    atm_gst = round2(atm_fee * 0.18)
    atm_tot = round2(atm_fee + atm_gst)
    bi_fee = round2(cur["biCount"] * 6)
    bi_gst = round2(bi_fee * 0.18)
    bi_tot = round2(bi_fee + bi_gst)
    m_fee = round2(cur["microAmt"] * 0.005)
    m_gst = round2(m_fee * 0.18)
    m_tot = round2(m_fee + m_gst)
    sw_cnt = cur["atmCount"] + cur["biCount"] + cur["microCount"]
    sw_fee = round4(sw_cnt * 0.30)
    sw_gst = round4(sw_fee * 0.18)
    sw_tot = round4(sw_fee + sw_gst)
    disp = cur["disputeAmt"] or 0.0
    sett_tot = round4(cur["atmAmt"] + atm_tot + cur["microAmt"] + m_tot + sw_tot - disp + bi_tot)
    return {
        "txnDate": cur["txnDate"], "finalAmt": cur["finalAmt"], "settTot": sett_tot,
        "atmCount": cur["atmCount"], "atmAmt": cur["atmAmt"], "atmFee": atm_fee, "atmFeeGST": atm_gst, "atmTotFee": atm_tot,
        "biCount": cur["biCount"], "biTot": bi_tot,
        "microCount": cur["microCount"], "microAmt": cur["microAmt"], "mFee": m_fee, "mGST": m_gst, "mTot": m_tot,
        "swCnt": sw_cnt, "swFee": sw_fee, "swGST": sw_gst, "swTot": sw_tot, "disp": disp,
        "cycleFromName": cur.get("cycleFromName"),
    }


def parse_ntsl_rows(rows: list[list[Any]], filename: str, is_html: bool) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None

    for row in rows:
        if not row:
            continue
        c0_raw = _get(row, 0)
        c0 = "" if c0_raw is None or isinstance(c0_raw, (datetime, date)) else str(c0_raw).strip()
        c0_lower = c0.lower()

        if "daily settlement statement" in c0_lower and "as on" in c0_lower:
            if cur and cur.get("finalAmt") is not None:
                blocks.append(_build_block(cur))
            block_date = extract_date(c0, row)
            if not block_date:
                cur = None
                continue
            cur = {
                "txnDate": block_date, "finalAmt": None, "atmCount": 0, "atmAmt": 0.0, "atmFee": None,
                "biCount": 0, "microAmt": 0.0, "microCount": 0, "disputeAmt": 0.0, "inDispute": False,
                "cycleFromName": cycle_from_filename(filename) if is_html else None,
            }
            continue

        if cur is None:
            continue
        if "dispute adjustment" in c0_lower:
            cur["inDispute"] = True
            continue
        if "summary for micro" in c0_lower:
            cur["inDispute"] = False
            continue

        if c0 == "Final Settlement Amount":
            for i in range(1, min(len(row), 6)):
                v = to_float(_get(row, i))
                if v > 0:
                    cur["finalAmt"] = v
                    break
        elif c0 == "Issuer WDL Transaction Amount":
            cur["atmCount"] = to_int(_get(row, 1))
            cur["atmAmt"] = to_float(_get(row, 2))
        elif c0 == "Issuer WDL Approved Fee" and "GST" not in c0 and "Micro" not in c0:
            cur["atmFee"] = to_float(_get(row, 2))
        elif c0 == "Issuer WDL Transaction Amount (Micro-ATM)":
            cur["microAmt"] = to_float(_get(row, 2))
        elif c0 == "Issuer WDLTransaction (Micro ATM)" and _get(row, 1) and "100 and above" in str(_get(row, 1)):
            cur["microCount"] += to_int(_get(row, 2))
        elif c0 == "Issuer BI Approved Fee" and "GST" not in c0:
            cur["biCount"] = to_int(_get(row, 1))
        elif cur["inDispute"] and c0 == "Adjustment Sub Totals":
            debit, credit = to_float(_get(row, 2)), to_float(_get(row, 3))
            if debit or credit:
                cur["disputeAmt"] = debit - credit
        elif cur["inDispute"] and c0 == "Net Adjusted Amount":
            v = to_float(_get(row, 2))
            if v != 0:
                cur["disputeAmt"] = v

    if cur and cur.get("finalAmt") is not None:
        blocks.append(_build_block(cur))
    return blocks


def assign_cycles(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    need_assign: list[dict[str, Any]] = []
    for b in blocks:
        if b.get("cycleFromName"):
            result.append({**b, "cycle": b["cycleFromName"]})
        else:
            need_assign.append(b)

    counter: dict[str, int] = {}
    for b in sorted(need_assign, key=lambda x: x["txnDate"]):
        key = fmt_d(b["txnDate"])
        counter[key] = counter.get(key, 0) + 1
        result.append({**b, "cycle": f"C{counter[key]}"})

    return sorted(result, key=lambda x: (x["txnDate"], x["cycle"]))


def parse_bank(rows: list[list[Any]]) -> list[dict[str, Any]]:
    header_idx = -1
    for i in range(min(8, len(rows))):
        norm = [str(v).lower().strip() if v else "" for v in (rows[i] or [])]
        if any("narrative" in v for v in norm) and any(v == "debit" for v in norm):
            header_idx = i
            break
    if header_idx < 0:
        return []

    header = [str(v).lower().strip() if v else "" for v in rows[header_idx]]
    idx_narr = next((i for i, h in enumerate(header) if "narrative" in h), -1)
    idx_debit = next((i for i, h in enumerate(header) if h == "debit"), -1)
    idx_date = next((i for i, h in enumerate(header) if "payment" in h or h == "date"), -1)
    idx_remark = next((i for i, h in enumerate(header) if "remark" in h), -1)

    entries: list[dict[str, Any]] = []
    for row in rows[header_idx + 1 :]:
        if not row or idx_narr < 0 or _get(row, idx_narr) is None:
            continue
        narrative = str(_get(row, idx_narr)).strip()
        if idx_remark >= 0 and _get(row, idx_remark) and str(_get(row, idx_remark)).strip().upper() != "NFS":
            continue
        if "NFS" not in narrative.upper():
            continue
        m = re.search(r"_00(\d{8})(\d{2})$", narrative.rstrip())
        if not m:
            continue
        txn_date = date(int(m.group(1)[0:4]), int(m.group(1)[4:6]), int(m.group(1)[6:8]))
        cycle = f"C{int(m.group(2))}"
        sett_date = _parse_any_date(_get(row, idx_date)) if idx_date >= 0 else None
        debit = to_float(_get(row, idx_debit)) if idx_debit >= 0 else 0.0
        if debit <= 0:
            continue
        entries.append(
            {"txnDate": txn_date, "cycle": cycle, "settDate": sett_date, "bankDebit": round2(debit), "narrative": narrative}
        )
    return entries


def _parse_any_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)):
        try:
            return (datetime(1899, 12, 30) + timedelta(days=float(v))).date()
        except (OverflowError, ValueError):
            return None
    if isinstance(v, str):
        s = v.strip()
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
    return None


DETAIL_COLUMNS = [
    "Date", "Cycle", "ATM Count", "ATM Amount", "ATM Fee", "ATM GST", "ATM Total Fee",
    "BI Count", "BI Total Fee", "Micro Count", "Micro Amount", "Micro Fee", "Micro GST", "Micro Total Fee",
    "Switch Count", "Switch Fee", "Switch GST", "Switch Total Fee", "Dispute Amount",
    "NTSL Final Amount", "Settlement Total (Recomputed)", "Bank Amount", "Settlement Date",
    "Difference (NTSL vs Bank)", "Status", "Bank Narrative",
]


class NFSModule(ReconModule):
    key = "nfs"
    display_name = "NFS Settlement Recon"
    description = "Reconciles NPCI NFS (ATM network) settlement statements against a bank statement, per T+1 cycle."
    version = "1.0.0"
    input_slots = [
        InputSlot(
            key="ntsl", label="NTSL Files", accept=[".xls", ".xlsx", ".xlsm"], multiple=True, required=True,
            help_text="Individual per-cycle files or one merged workbook; HTML-formatted NPCI exports are auto-detected.",
        ),
        InputSlot(key="bank", label="Bank Statement", accept=[".xlsx", ".xls", ".xlsm"], required=True),
    ]
    options_schema = NFSOptions

    def parse(self, ctx: RunContext) -> ParsedData:
        ntsl_files = ctx.files_for("ntsl")
        bank_file = ctx.files_for("bank")[0]

        blocks: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        for f in ntsl_files:
            try:
                is_html = sniff_format(f.content) == "html"
                rows = read_rows(f.content, f.filename)
                file_blocks = parse_ntsl_rows(rows, f.filename, is_html)
                if file_blocks:
                    blocks.extend(file_blocks)
                else:
                    skipped.append({"file": f.filename, "reason": "no settlement block recognized"})
            except Exception as exc:  # noqa: BLE001
                skipped.append({"file": f.filename, "reason": str(exc)})

        bank_rows = read_rows(bank_file.content, bank_file.filename)
        bank_entries = parse_bank(bank_rows)

        ctx.info(f"Parsed {len(blocks)} NTSL block(s) from {len(ntsl_files)} file(s), {len(bank_entries)} NFS bank entries")
        return ParsedData(data={"blocks": blocks, "bank_entries": bank_entries, "skipped": skipped, "file_count": len(ntsl_files)})

    def validate(self, parsed: ParsedData, ctx: RunContext) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        if not parsed.data["blocks"]:
            findings.append(ValidationFinding(pass_name="Input Integrity", check="NTSL blocks", level="err", message="No NTSL blocks parsed"))
        else:
            findings.append(
                ValidationFinding(pass_name="Input Integrity", check="NTSL blocks", level="ok", message=f"{len(parsed.data['blocks'])} block(s) parsed")
            )
        if not parsed.data["bank_entries"]:
            findings.append(ValidationFinding(pass_name="Input Integrity", check="Bank entries", level="err", message="No NFS bank entries found"))
        if parsed.data["skipped"]:
            findings.append(
                ValidationFinding(pass_name="Input Integrity", check="Skipped files", level="warn", message=f"{len(parsed.data['skipped'])} file(s) skipped")
            )
        return findings

    def reconcile(self, parsed: ParsedData, ctx: RunContext, findings: list[ValidationFinding]) -> ReconOutput:
        if any(f.level == "err" for f in findings):
            return ReconOutput(stats=[StatCard(label="Status", value="Failed pre-checks", tone="bad")])

        options = NFSOptions(**ctx.options)
        all_ntsl = assign_cycles(parsed.data["blocks"])
        ntsl = [b for b in all_ntsl if not options.month or fmt_mo(b["txnDate"]) == options.month]
        if not ntsl:
            return ReconOutput(stats=[StatCard(label="Status", value="No NTSL cycles after month filter", tone="bad")])

        scope_months = {fmt_mo(b["txnDate"]) for b in ntsl}
        bank_entries = parsed.data["bank_entries"]
        bank_in = [b for b in bank_entries if fmt_mo(b["txnDate"]) in scope_months]
        carry = [b for b in bank_entries if fmt_mo(b["txnDate"]) not in scope_months]

        bank_map: dict[str, dict[str, Any]] = {}
        for b in bank_in:
            bank_map[f"{fmt_d(b['txnDate'])}_{b['cycle']}"] = b  # last-write-wins, matches source

        recon_rows: list[dict[str, Any]] = []
        for n in ntsl:
            key = f"{fmt_d(n['txnDate'])}_{n['cycle']}"
            bk = bank_map.get(key)
            ntsl_amt = n["finalAmt"]
            bank_amt = bk["bankDebit"] if bk else None
            diff_val = round4(ntsl_amt - bank_amt) if bank_amt is not None else None
            if bank_amt is None:
                status = "PENDING"
            elif abs(diff_val) <= options.threshold:
                status = "MATCHED"
            elif diff_val < 0:
                status = "EXCESS DEBIT"
            else:
                status = "DEFICIT"
            sett_date = bk["settDate"] if bk and bk.get("settDate") else n["txnDate"] + timedelta(days=1)

            recon_rows.append(
                {
                    "Date": n["txnDate"].isoformat(), "Cycle": n["cycle"],
                    "ATM Count": n["atmCount"], "ATM Amount": n["atmAmt"], "ATM Fee": n["atmFee"],
                    "ATM GST": n["atmFeeGST"], "ATM Total Fee": n["atmTotFee"],
                    "BI Count": n["biCount"], "BI Total Fee": n["biTot"],
                    "Micro Count": n["microCount"], "Micro Amount": n["microAmt"], "Micro Fee": n["mFee"],
                    "Micro GST": n["mGST"], "Micro Total Fee": n["mTot"],
                    "Switch Count": n["swCnt"], "Switch Fee": n["swFee"], "Switch GST": n["swGST"], "Switch Total Fee": n["swTot"],
                    "Dispute Amount": n["disp"],
                    "NTSL Final Amount": ntsl_amt, "Settlement Total (Recomputed)": n["settTot"],
                    "Bank Amount": bank_amt, "Settlement Date": sett_date.isoformat() if sett_date else None,
                    "Difference (NTSL vs Bank)": diff_val, "Status": status,
                    "Bank Narrative": bk["narrative"] if bk else None,
                }
            )

        daily: dict[str, dict[str, Any]] = {}
        for r in recon_rows:
            k = r["Date"]
            d = daily.setdefault(
                k, {"Date": k, "ATM Count": 0, "ATM Amount": 0.0, "ATM Total Fee": 0.0, "Micro Amount": 0.0,
                    "Switch Count": 0, "Settlement Total": 0.0, "Bank Total": 0.0, "Has Bank": False}
            )
            d["ATM Count"] += r["ATM Count"]
            d["ATM Amount"] += r["ATM Amount"]
            d["ATM Total Fee"] += r["ATM Total Fee"]
            d["Micro Amount"] += r["Micro Amount"]
            d["Switch Count"] += r["Switch Count"]
            d["Settlement Total"] += r["Settlement Total (Recomputed)"]
            if r["Bank Amount"] is not None:
                d["Bank Total"] += r["Bank Amount"]
                d["Has Bank"] = True
        daily_rows = []
        for d in sorted(daily.values(), key=lambda x: x["Date"]):
            diff = round4(d["Settlement Total"] - d["Bank Total"]) if d["Has Bank"] else None
            daily_rows.append(
                {
                    "Date": d["Date"], "ATM Count": d["ATM Count"], "ATM Amount": round2(d["ATM Amount"]),
                    "ATM Total Fee": round2(d["ATM Total Fee"]), "Micro Amount": round2(d["Micro Amount"]),
                    "Switch Count": d["Switch Count"], "Settlement Total": round2(d["Settlement Total"]),
                    "Bank Total": round2(d["Bank Total"]) if d["Has Bank"] else None, "Difference": diff,
                }
            )

        matched = [r for r in recon_rows if r["Status"] == "MATCHED"]
        pending = [r for r in recon_rows if r["Status"] == "PENDING"]
        diffs = [r for r in recon_rows if r["Status"] in ("EXCESS DEBIT", "DEFICIT")]
        ntsl_total = round2(sum(r["NTSL Final Amount"] for r in recon_rows))
        bank_total = round2(sum(r["Bank Amount"] for r in recon_rows if r["Bank Amount"] is not None))

        stats = [
            StatCard(label="Total Cycles", value=str(len(recon_rows)), sub=f"{len({r['Date'] for r in recon_rows})} days"),
            StatCard(label="Matched", value=str(len(matched)), tone="good"),
            StatCard(label="Pending (T+1)", value=str(len(pending)), tone="warn" if pending else "good"),
            StatCard(label=f"Differences (>₹{options.threshold:.0f})", value=str(len(diffs)), tone="bad" if diffs else "good"),
            StatCard(label="NTSL Total", value=f"₹{ntsl_total:,.2f}"),
            StatCard(label="Bank Total", value=f"₹{bank_total:,.2f}"),
        ]

        exception_rows = [r for r in recon_rows if r["Status"] != "MATCHED"]
        carry_rows = [
            {"Date": b["txnDate"].isoformat(), "Cycle": b["cycle"], "Bank Debit": b["bankDebit"], "Narrative": b["narrative"]}
            for b in carry
        ]

        sheets = [
            ReportSheet(name="NFS Recon Cycle", kind="detail", columns=DETAIL_COLUMNS, rows=recon_rows),
            ReportSheet(name="Daily Summary", kind="summary", columns=list(daily_rows[0].keys()) if daily_rows else [], rows=daily_rows),
            ReportSheet(name="Exceptions", kind="exception", columns=DETAIL_COLUMNS, rows=exception_rows),
        ]
        if carry_rows:
            sheets.append(ReportSheet(name="Carry Over", kind="exception", columns=["Date", "Cycle", "Bank Debit", "Narrative"], rows=carry_rows))

        return ReconOutput(
            stats=stats, sheets=sheets, findings=[],
            raw={"detail_columns": DETAIL_COLUMNS, "detail_rows": recon_rows, "daily_rows": daily_rows, "carry_rows": carry_rows},
        )

    def build_report(self, output: ReconOutput, ctx: RunContext) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = "NFS Recon Cycle"
        columns = output.raw["detail_columns"]
        set_column_widths(ws, {1: 12, 2: 8} | {i: 14 for i in range(3, len(columns) + 1)})
        for i, name in enumerate(columns, start=1):
            set_cell(ws, 1, i, name, fill=solid_fill("FFBDD7EE"))
            bold_font(ws.cell(row=1, column=i))
        freeze(ws, "C2")

        green = solid_fill("FFC6EFCE")
        red = solid_fill("FFFFC7CE")
        blue = solid_fill("FFDDEBF7")
        status_col = columns.index("Status") + 1
        row_idx = 2
        for row in output.raw["detail_rows"]:
            write_row(ws, row_idx, [row.get(c) for c in columns])
            status = row["Status"]
            cell = ws.cell(row=row_idx, column=status_col)
            cell.fill = green if status == "MATCHED" else (blue if status == "PENDING" else red)
            row_idx += 1

        data_end = row_idx - 1
        total_row = row_idx
        set_cell(ws, total_row, 2, "TOTAL", fill=solid_fill("FFD9E1F2"))
        for label in ["ATM Amount", "NTSL Final Amount", "Settlement Total (Recomputed)", "Bank Amount"]:
            col = columns.index(label) + 1
            letter = ws.cell(row=1, column=col).column_letter
            set_cell(ws, total_row, col, f"=SUM({letter}2:{letter}{data_end})", fill=solid_fill("FFD9E1F2"))

        daily_ws = wb.create_sheet("Daily Summary")
        daily_rows = output.raw["daily_rows"]
        if daily_rows:
            daily_cols = list(daily_rows[0].keys())
            for i, name in enumerate(daily_cols, start=1):
                set_cell(daily_ws, 1, i, name, fill=solid_fill("FFBDD7EE"))
            for r_i, row in enumerate(daily_rows, start=2):
                write_row(daily_ws, r_i, [row.get(c) for c in daily_cols])
            set_column_widths(daily_ws, {i: 16 for i in range(1, len(daily_cols) + 1)})

        exceptions_ws = wb.create_sheet("Exceptions")
        for i, name in enumerate(columns, start=1):
            set_cell(exceptions_ws, 1, i, name, fill=solid_fill("FFB71C1C"))
            bold_font(exceptions_ws.cell(row=1, column=i), color="FFFFFFFF")
        r_i = 2
        for row in output.raw["detail_rows"]:
            if row["Status"] == "MATCHED":
                continue
            write_row(exceptions_ws, r_i, [row.get(c) for c in columns])
            r_i += 1
        set_column_widths(exceptions_ws, {i: 14 for i in range(1, len(columns) + 1)})

        if output.raw["carry_rows"]:
            carry_ws = wb.create_sheet("Carry Over")
            carry_cols = ["Date", "Cycle", "Bank Debit", "Narrative"]
            for i, name in enumerate(carry_cols, start=1):
                set_cell(carry_ws, 1, i, name, fill=solid_fill("FFFFE0B2"))
            for r_i, row in enumerate(output.raw["carry_rows"], start=2):
                write_row(carry_ws, r_i, [row.get(c) for c in carry_cols])
            set_column_widths(carry_ws, {1: 12, 2: 8, 3: 14, 4: 40})

        import io

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()


register(NFSModule())
