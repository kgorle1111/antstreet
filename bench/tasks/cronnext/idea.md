Create a Python module `cronnext.py` (standard library only) that finds when a small subset of
cron expressions fires next. It provides two functions:

    next_fire(expr: str, after: datetime) -> datetime
    next_fires(expr: str, after: datetime, count: int) -> list[datetime]

All datetimes are naive (no time zone), and the module never reads the clock: the starting point
is always passed in.

The expression:

1. `expr` has five fields separated by one or more spaces or tabs, in this order: minute (0-59),
   hour (0-23), day of month (1-31), month (1-12) and day of week (0-6, where 0 is Sunday, 1 is
   Monday and 6 is Saturday). Whitespace around the whole expression is ignored.
2. A field is a comma-separated list of one or more items, and the field matches a value if any
   item does. An item is `*` (every value the field allows), a number, or a range `a-b` (both ends
   included, `a` not larger than `b`). A `*` or a range may be followed by `/step`, where `step` is
   a whole number of at least 1: it keeps every `step`-th value counting from the first value of
   the item, which for `*` is the lowest value the field allows. So `*/15` in the minute field is
   0, 15, 30 and 45, `*/10` in the day-of-month field is 1, 11, 21 and 31, `*/5` in the month field
   is 1, 6 and 11, and `1-5/2` is 1, 3 and 5. A single number cannot take a step (`5/10` is
   invalid). A step larger than the range is fine (`*/60` in the minute field is just 0).
3. Numbers are one or more ASCII digits, and leading zeros are fine (`05`). Month names, weekday
   names, `@daily` and similar shortcuts, `?`, signs and any other characters are not supported.
4. The minute, hour and month fields must all match. The day is decided by the day-of-month and
   day-of-week fields together: if neither field is written exactly as `*`, a day matches when it
   satisfies either of them (the way classic cron works), so `0 0 13 * 5` fires on every 13th and
   on every Friday. If one of the two fields is written exactly as `*`, only the other one is
   used, and if both are `*` every day matches.
5. A day of the month that a month does not have simply never matches in that month: `0 0 31 * *`
   fires only in months with 31 days, and `0 0 29 2 *` only in leap years (Gregorian rule: 2100
   is not a leap year, 2000 and 2024 are). A day-of-month value that never exists still allows the
   day-of-week half of rule 4 to fire: `0 0 31 2 1` fires on Mondays in February.

Functions:

6. `next_fire(expr, after)` returns the earliest datetime `t` that is strictly later than `after`,
   has second 0 and microsecond 0, and matches the expression. Only the minute of `after` counts:
   after 10:30:00 or 10:30:45, the expression `30 10 * * *` next fires on the following day, while
   after 10:29:59.999999 it fires at 10:30 the same day. The result is a naive `datetime`.
7. If the expression has no match within the 3660 days after `after`, `next_fire` raises
   `ValueError`; `0 0 31 2 *` is an example that never fires.
8. `next_fires(expr, after, count)` returns a list of the next `count` fire times: the first is
   `next_fire(expr, after)` and each following one is `next_fire` of the one before it, so the list
   is strictly increasing. `count` of 0 gives an empty list without searching, so even a
   never-firing expression returns `[]`. The expression is still checked when `count` is 0.
9. `ValueError` is raised for an expression that is not valid under rules 1 to 3: the wrong number
   of fields (including the empty string), an empty item (`1,,2`, `1,`), a value outside the field's
   range, a reversed range, a step of 0, a step on a single number, and any other text. A
   negative `count` and an `after` that has a time zone (`tzinfo` is not None) also raise
   `ValueError`.
10. `TypeError` is raised when `expr` is not a `str`, when `after` is not a `datetime.datetime`
    (a plain `date` is not one), and when `count` is not an `int` (a `bool` is not).
