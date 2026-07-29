"""Shared matching primitives used by every module: keyed aggregation with
duplicate-key summation (the pattern every source tool implements via a
Scripting.Dictionary / JS object: `dict[key] = (dict[key] || 0) + amount`).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class KeyedAggregator:
    """Sums an amount per key, remembering the first row index a key was
    seen at (used for "highlight the first matching source row" parity
    with the VBA macros, and for exposing which file/row a value came from)."""

    amounts: dict[str, float] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    first_row: dict[str, int] = field(default_factory=dict)

    def add(self, key: str, amount: float = 0.0, row_index: int = -1) -> None:
        if not key:
            return
        self.amounts[key] = self.amounts.get(key, 0.0) + amount
        self.counts[key] = self.counts.get(key, 0) + 1
        if key not in self.first_row and row_index >= 0:
            self.first_row[key] = row_index

    def get(self, key: str) -> float | None:
        return self.amounts.get(key)

    def exists(self, key: str) -> bool:
        return key in self.amounts

    def keys(self) -> list[str]:
        return list(self.amounts.keys())


def diff(a: float, b: float) -> float:
    return a - b
