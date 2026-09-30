import calendar
from collections.abc import Iterable
from datetime import date, datetime, timedelta


def _require_date(value: object) -> None:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"expected datetime.date, got {type(value).__name__}")


def _require_int(value: object) -> None:
    if not isinstance(value, int):
        raise TypeError(f"expected int, got {type(value).__name__}")


def add_months(d: date, months: int) -> date:
    _require_date(d)
    _require_int(months)
    year, month0 = divmod(d.year * 12 + d.month - 1 + months, 12)
    last_day = calendar.monthrange(year, month0 + 1)[1]
    return date(year, month0 + 1, min(d.day, last_day))


def business_days_between(start: date, end: date, holidays: Iterable[date] = ()) -> int:
    _require_date(start)
    _require_date(end)
    if end < start:
        return -business_days_between(end, start, holidays)
    weeks, extra = divmod((end - start).days, 7)
    count = weeks * 5 + sum(1 for i in range(extra) if (start.weekday() + i) % 7 < 5)
    return count - len({h for h in holidays if start <= h < end and h.weekday() < 5})


def add_business_days(d: date, n: int, holidays: Iterable[date] = ()) -> date:
    _require_date(d)
    _require_int(n)
    skip = set(holidays)
    step = timedelta(days=1 if n > 0 else -1)
    remaining = abs(n)
    while remaining:
        d += step
        if d.weekday() < 5 and d not in skip:
            remaining -= 1
    return d
