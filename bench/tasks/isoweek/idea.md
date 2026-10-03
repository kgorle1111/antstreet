Create a Python module `isoweek.py` (standard library only) that works on `datetime.date` values
and provides four functions:

    iso_week(d: date) -> tuple[int, int]
    weeks_in_year(year: int) -> int
    format_iso_week(d: date) -> str
    parse_iso_week(text: str) -> date

It implements ISO 8601 week dates. Weeks run from Monday to Sunday. Week 1 of a year is the week
(Monday to Sunday) that contains January 4th of that year. Every date belongs to exactly one week
of exactly one "ISO year", and that is not always its calendar year: a date in early January can
belong to the last week of the previous ISO year, and a date in late December can belong to week 1
of the next one. The weekday is numbered 1 for Monday to 7 for Sunday.

1. `iso_week(d)` returns `(iso_year, week)` as two ints, where `week` is 1 to 53. For example
   2021-01-03 (a Sunday) is `(2020, 53)`, 2021-01-04 is `(2021, 1)`, and 2024-12-30 is `(2025, 1)`.
2. `weeks_in_year(year)` is the number of the last week of that ISO year, which is 52 or 53. It
   accepts years 1 to 9999; any other int raises `ValueError`.
3. `format_iso_week(d)` returns the ISO week date as `YYYY-Www-D`: the ISO year (not the calendar
   year) as four digits padded with zeros, a capital `W`, the week as two digits padded with a
   zero, and the weekday as one digit. 2021-01-03 is `2020-W53-7`, 2024-03-15 is `2024-W11-5`, and
   0001-01-01 is `0001-W01-1`. There are no spaces.
4. `parse_iso_week(text)` is the inverse and returns the date. The text must match the format of
   rule 3 exactly: four ASCII digits, `-W`, two ASCII digits, `-`, one ASCII digit, with nothing
   before, after or between (no whitespace, no lowercase `w`, no other digits than 0-9). It raises
   `ValueError` when the text does not match, when the year is `0000`, when the week is `00` or
   larger than `weeks_in_year(year)`, when the weekday is not 1 to 7, and when the date would fall
   outside the range of `datetime.date` (for example `9999-W52-7`).
5. `iso_week` and `format_iso_week` take a `datetime.date`. A `datetime.datetime` is not accepted
   even though it is a subclass of `date`. Any argument that is not a date raises `TypeError`.
   `parse_iso_week` raises `TypeError` for anything that is not a `str`, and `weeks_in_year` raises
   `TypeError` for anything that is not an `int` (a `bool`, a float and a str are not).
6. For every date `d`, `parse_iso_week(format_iso_week(d)) == d`.
