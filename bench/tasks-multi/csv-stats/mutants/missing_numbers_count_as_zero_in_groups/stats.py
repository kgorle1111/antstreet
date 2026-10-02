# group_by treats a missing number as 0.0 instead of skipping it, so counts and means include it.
import math
import statistics
from dataclasses import dataclass

_FUNCS = ("sum", "mean", "count", "min", "max")


@dataclass(frozen=True)
class Summary:
    count: int
    missing: int
    mean: float | None
    minimum: float | None
    maximum: float | None
    median: float | None
    stdev: float | None


def describe(values):
    values = list(values)
    present = [float(v) for v in values if v is not None]
    missing = len(values) - len(present)
    if not present:
        return Summary(0, missing, None, None, None, None, None)
    stdev = statistics.stdev(present) if len(present) >= 2 else None
    return Summary(
        len(present),
        missing,
        math.fsum(present) / len(present),
        min(present),
        max(present),
        float(statistics.median(present)),
        stdev,
    )


def _aggregate(func, numbers):
    if func == "count":
        return len(numbers)
    if func == "sum":
        return math.fsum(numbers)
    if not numbers:
        return None
    if func == "mean":
        return math.fsum(numbers) / len(numbers)
    return min(numbers) if func == "min" else max(numbers)


def group_by(table, key, value, func="sum"):
    if func not in _FUNCS:
        raise ValueError(f"func must be one of {_FUNCS}")
    keys = table.column(key)
    numbers = table.numbers(value)
    groups = {}
    for group, number in zip(keys, numbers, strict=True):
        found = groups.setdefault(group, [])
        found.append(0.0 if number is None else number)
    return {group: _aggregate(func, found) for group, found in groups.items()}
