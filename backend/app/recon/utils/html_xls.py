"""Parser for NPCI's HTML-formatted "XLS" exports (used by the NFS module).

The original tool scraped these with hand-rolled regexes over the raw HTML
string ("50x faster than DOMParser" per its own comment, because the
in-browser DOMParser choked on hundreds of files). Server-side we have no
such constraint, so we use a real HTML parser (lxml via BeautifulSoup) -
more robust against attribute/whitespace variation than regex scraping,
per ARCHITECTURE.md's rationale for the Python port.
"""
from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup


def parse_html_table(data: bytes) -> list[list[Any]]:
    """Return the first HTML table's rows as a list of cell-text lists,
    matching the shape of `XLSX.utils.sheet_to_json(ws, {header:1})` used
    throughout the source tools: one row per <tr>, one cell per <td>/<th>,
    blank cells as None.
    """
    soup = BeautifulSoup(data, "lxml")
    table = soup.find("table")
    if table is None:
        return []

    rows: list[list[Any]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        rows.append([_cell_value(cell) for cell in cells])
    return rows


def _cell_value(cell) -> Any:
    text = cell.get_text(strip=True)
    return text if text != "" else None


def looks_like_html(data: bytes) -> bool:
    head = data[:2048].lstrip().lower()
    return head.startswith(b"<html") or head.startswith(b"<!doctype") or b"<table" in head
