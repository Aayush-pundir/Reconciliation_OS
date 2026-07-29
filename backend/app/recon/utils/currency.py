"""Financial rounding/parsing helpers that reproduce the exact semantics of
the source tools' JS (`Math.round(x*100)/100`) and VBA (`CDbl`) code, since
financial rounding must match observed behavior, not just be "close enough".

`Math.round` in JS rounds half **towards positive infinity** for every x
(so `Math.round(-0.5) === 0`, `Math.round(-1.5) === -1`). `math.floor(x+0.5)`
reproduces that exact behavior for both positive and negative inputs, unlike
Python's built-in `round()` which uses banker's rounding.
"""
from __future__ import annotations

import math
from typing import Any


def to_float(value: Any) -> float:
    """Safe numeric coercion - mirrors the `sf`/`toF`/`toN` helpers used
    throughout the source tools: never raises, blank/garbage -> 0.0."""
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return 0.0 if isinstance(value, float) and math.isnan(value) else float(value)
    text = str(value).strip().replace(",", "")
    if text == "":
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def to_int(value: Any) -> int:
    return int(round(to_float(value)))


def _js_round(value: float) -> float:
    return math.floor(value + 0.5) if value >= 0 else -math.floor(-value + 0.5)


def round2(value: Any) -> float:
    return _js_round(to_float(value) * 100) / 100


def round4(value: Any) -> float:
    return _js_round(to_float(value) * 10000) / 10000
