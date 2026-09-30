Create a Python module `duration.py` (standard library only) with two functions:

    parse_duration(text: str) -> float
    format_duration(seconds: float) -> str

`parse_duration` turns strings such as `1h30m`, `90s`, `2d 4h`, `1.5h` and `250ms` into a number of
seconds. `format_duration` is its canonical inverse.

Parsing:

1. The units are `w` (week, 7 days), `d` (day), `h` (hour), `m` (minute), `s` (second) and `ms`
   (millisecond). Units are lowercase only; `1H` is invalid. `5m` is five minutes and `5ms` is
   five milliseconds. The result is a `float`.
2. A duration is one or more components, each a number immediately followed by its unit, and the
   results are added: `1h30m` is 5400 seconds and `1m5ms` is 60.005 seconds.
3. Components must appear in strictly descending unit order (w, d, h, m, s, ms) and each unit may
   appear at most once. Units may be skipped: `1w5s` is valid, `30s1m` and `1h1h` are not.
4. A number is one or more ASCII digits 0-9, optionally followed by a `.` and one or more digits:
   `1.5` is valid, while `.5`, `1.`, `1.5.5`, `1e3`, `1_0` and non-ASCII digits are not. Any
   component may be decimal, not only the last: `1.5h30m` is 7200 seconds.
5. Whitespace may appear between components (`2d 4h`, `2d  4h`, and tabs count) and around the
   whole string, but never between a number and its unit (`1 h` is invalid) or between a leading
   minus sign and the first number.
6. A single leading `-` negates the whole duration: `-1h30m` is -5400 seconds. `-0s` is 0.
7. `parse_duration` raises `ValueError` for anything that does not follow these rules, including:
   the empty string or a string of only whitespace, a number without a unit (`30`, `1h30`), a unit
   without a number, an unknown unit (`1x`, `1hr`, `1H`), repeated or out-of-order units, a sign
   anywhere except at the very start, a second leading sign (`--1s`), and any other characters.
   Input that is not a `str` (an int, a float, None, bytes) also raises `ValueError`.

Formatting:

8. `format_duration` accepts an int or a float, negative values included. It first rounds the
   absolute value to the nearest whole millisecond (exact ties are not specified), then splits it
   into weeks, days, hours, minutes, seconds and milliseconds, using as many weeks as fit (there
   is no larger unit) and so on down. Rounding happens before splitting, so 59.9996 seconds is
   `1m`, not `59s1000ms`.
9. The output lists the components largest unit first, with no separators between them, and omits
   every component that is zero: 3601 seconds is `1h1s`, 90 seconds is `1m30s`, 1.5 seconds is
   `1s500ms`, 0.25 seconds is `250ms`. All components are whole numbers.
10. If the rounded value is zero the result is `0s`, with no sign. Otherwise a negative input gets
    a leading `-` (-90 is `-1m30s`).
11. For any x, `parse_duration(format_duration(x))` equals x to the nearest millisecond.
