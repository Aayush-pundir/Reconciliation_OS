"""Styled-worksheet helpers shared by every module's `build_report()`, so
the merged-group-header / frozen-pane / conditional-fill / live-formula
look of the original ExcelJS-built reports (NFS, RuPay, UPI) is achieved
with a handful of reusable primitives instead of being re-implemented
per module.
"""
from __future__ import annotations

from typing import Any, Iterable

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

THIN = Side(style="thin", color="FFBFBFBF")
BORDER_THIN = Border(top=THIN, left=THIN, bottom=THIN, right=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center")
RIGHT = Alignment(horizontal="right", vertical="center")


def bold_font(cell, color: str | None = None) -> None:
    """Rebuild a cell's font with bold=True, preserving its other attributes.
    (openpyxl's `Font.copy()` is deprecated; this is the direct replacement.)"""
    f = cell.font
    cell.font = Font(name=f.name, size=f.size, bold=True, color=color or f.color)


def solid_fill(argb: str) -> PatternFill:
    """`argb` like 'FFC6EFCE' (alpha+RGB hex, openpyxl convention)."""
    return PatternFill("solid", fgColor=argb)


def font(color: str = "FF1A1A1A", bold: bool = False, size: int = 10, name: str = "Calibri") -> Font:
    return Font(name=name, size=size, bold=bold, color=color)


def write_row(
    ws: Worksheet,
    row_idx: int,
    values: Iterable[Any],
    *,
    start_col: int = 1,
    cell_font: Font | None = None,
    fill: PatternFill | None = None,
    number_format: str | None = None,
    border: bool = True,
    align: Alignment | None = None,
) -> None:
    for offset, value in enumerate(values):
        col = start_col + offset
        cell = ws.cell(row=row_idx, column=col, value=value)
        if cell_font:
            cell.font = cell_font
        if fill:
            cell.fill = fill
        if number_format:
            cell.number_format = number_format
        if border:
            cell.border = BORDER_THIN
        if align:
            cell.alignment = align


def set_cell(
    ws: Worksheet,
    row: int,
    col: int,
    value: Any,
    *,
    cell_font: Font | None = None,
    fill: PatternFill | None = None,
    number_format: str | None = None,
    border: bool = True,
    align: Alignment | None = None,
) -> None:
    cell = ws.cell(row=row, column=col, value=value)
    if cell_font:
        cell.font = cell_font
    if fill:
        cell.fill = fill
    if number_format:
        cell.number_format = number_format
    if border:
        cell.border = BORDER_THIN
    if align:
        cell.alignment = align


def merge_and_label(
    ws: Worksheet,
    row1: int,
    col1: int,
    row2: int,
    col2: int,
    value: Any,
    *,
    cell_font: Font | None = None,
    fill: PatternFill | None = None,
    align: Alignment | None = None,
) -> None:
    """Merge a rectangular block and label its top-left cell - used for the
    3-row merged group/sub-group/column headers in NFS/RuPay/UPI reports."""
    if row1 != row2 or col1 != col2:
        ws.merge_cells(start_row=row1, start_column=col1, end_row=row2, end_column=col2)
    cell = ws.cell(row=row1, column=col1, value=value)
    if cell_font:
        cell.font = cell_font
    if fill:
        cell.fill = fill
    cell.alignment = align or CENTER
    for r in range(row1, row2 + 1):
        for c in range(col1, col2 + 1):
            ws.cell(row=r, column=c).border = BORDER_THIN


def set_column_widths(ws: Worksheet, widths: dict[int, float]) -> None:
    for col, width in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = width


def freeze(ws: Worksheet, cell: str) -> None:
    ws.freeze_panes = cell


def col_letter(idx: int) -> str:
    return get_column_letter(idx)
