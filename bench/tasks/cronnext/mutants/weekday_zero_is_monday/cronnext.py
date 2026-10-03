# Day of week uses Python's numbering (0 is Monday, 6 is Sunday) instead of 0 for Sunday.
import re
from datetime import datetime, timedelta

_LIMITS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))
_ITEM = re.compile(r"(\*|([0-9]+)(?:-([0-9]+))?)(?:/([0-9]+))?")
_SEARCH_DAYS = 3660


def _parse_field(text: str, low: int, high: int) -> list[int]:
    values: set[int] = set()
    for item in text.split(","):
        match = _ITEM.fullmatch(item)
        if match is None:
            raise ValueError(f"bad cron item {item!r}")
        whole, start, end, step = match.groups()
        if whole == "*":
            first, last = low, high
        elif end is None:
            if step is not None:
                raise ValueError(f"a single number cannot take a step: {item!r}")
            first = last = int(start)
        else:
            first, last = int(start), int(end)
        stride = 1 if step is None else int(step)
        if stride < 1:
            raise ValueError(f"step must be at least 1: {item!r}")
        if not low <= first <= last <= high:
            raise ValueError(f"{item!r} is outside {low}-{high}")
        values.update(range(first, last + 1, stride))
    return sorted(values)


def _parse(expr: str) -> tuple[list[list[int]], bool, bool]:
    if not isinstance(expr, str):
        raise TypeError(f"expression must be a str, got {type(expr).__name__}")
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"expected 5 fields, got {len(parts)}")
    fields = [_parse_field(p, lo, hi) for p, (lo, hi) in zip(parts, _LIMITS, strict=True)]
    return fields, parts[2] == "*", parts[4] == "*"


def next_fire(expr: str, after: datetime) -> datetime:
    (minutes, hours, days, months, weekdays), dom_star, dow_star = _parse(expr)
    if not isinstance(after, datetime):
        raise TypeError(f"after must be a datetime, got {type(after).__name__}")
    if after.tzinfo is not None:
        raise ValueError("after must be naive")
    start = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = after + timedelta(days=_SEARCH_DAYS)
    day = start.replace(hour=0, minute=0)
    while day <= limit:
        if day.month in months:
            dom = day.day in days
            dow = day.weekday() in weekdays
            if (dom or dow) if not (dom_star or dow_star) else (dom and dow):
                for hour in hours:
                    for minute in minutes:
                        fire = day.replace(hour=hour, minute=minute)
                        if fire >= start:
                            if fire > limit:
                                raise ValueError(f"{expr!r} does not fire within the search window")
                            return fire
        day += timedelta(days=1)
    raise ValueError(f"{expr!r} does not fire within the search window")


def next_fires(expr: str, after: datetime, count: int) -> list[datetime]:
    _parse(expr)
    if isinstance(count, bool) or not isinstance(count, int):
        raise TypeError(f"count must be an int, got {type(count).__name__}")
    if count < 0:
        raise ValueError("count must not be negative")
    fires: list[datetime] = []
    moment = after
    for _ in range(count):
        moment = next_fire(expr, moment)
        fires.append(moment)
    return fires
