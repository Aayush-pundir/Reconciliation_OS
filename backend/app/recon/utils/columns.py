"""Case-insensitive header lookup - mirrors every source tool's `FindCol`/
`fi(...)` dynamic-header-by-name pattern (never assumes fixed column
positions)."""
from __future__ import annotations


def find_col(headers: list[str], name: str) -> str | None:
    target = name.strip().lower()
    for h in headers:
        if h.strip().lower() == target:
            return h
    return None
