"""Interval maths and the report formatting every benchmark and role shares.

Imports nothing from antstreet: roles and bench both sit above it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    low = 0.0 if successes == 0 else max(0.0, centre - margin)
    high = 1.0 if successes == n else min(1.0, centre + margin)
    return (low, high)


def pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def pct_interval(p: float, low: float, high: float) -> str:
    return f"{pct(p)} [{low * 100:.0f}-{high * 100:.0f}%]"


def rate(
    successes: int,
    n: int,
    *,
    counts: Literal["none", "before", "after"] = "none",
    empty: str | None = None,
) -> str:
    """`P% [low-high%]` with its Wilson interval; `counts` puts `s/n` before (`s/n = `) or after
    (` (s/n)`) it. With `empty` set, n == 0 gives that text; without it n must be positive."""
    if n == 0 and empty is not None:
        return empty
    text = pct_interval(successes / n, *wilson_interval(successes, n))
    if counts == "before":
        return f"{successes}/{n} = {text}"
    if counts == "after":
        return f"{text} ({successes}/{n})"
    return text


def md_table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    def line(cells: Sequence[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    return [line(header), line(["---"] * len(header))] + [line(r) for r in rows]
