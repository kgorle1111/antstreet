# weeks_in_year says 53 only when January 1st is a Thursday and forgets leap years that start on a Wednesday.
import re
from datetime import date, datetime

_FORMAT = re.compile(r"([0-9]{4})-W([0-9]{2})-([0-9])")


def _require_date(d: object) -> date:
    if not isinstance(d, date) or isinstance(d, datetime):
        raise TypeError(f"expected a date, got {type(d).__name__}")
    return d


def iso_week(d: date) -> tuple[int, int]:
    year, week, _ = _require_date(d).isocalendar()
    return year, week


def weeks_in_year(year: int) -> int:
    if isinstance(year, bool) or not isinstance(year, int):
        raise TypeError(f"year must be an int, got {type(year).__name__}")
    if not 1 <= year <= 9999:
        raise ValueError(f"year {year} is outside 1..9999")
    # Dec 28 is always in the last week of its ISO year.
    return 53 if date(year, 1, 1).weekday() == 3 else 52


def format_iso_week(d: date) -> str:
    year, week, weekday = _require_date(d).isocalendar()
    return f"{year:04d}-W{week:02d}-{weekday}"


def parse_iso_week(text: str) -> date:
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    match = _FORMAT.fullmatch(text)
    if match is None:
        raise ValueError(f"not an ISO week date: {text!r}")
    year, week, weekday = (int(part) for part in match.groups())
    return date.fromisocalendar(year, week, weekday)
