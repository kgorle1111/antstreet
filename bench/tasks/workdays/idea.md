Create a Python module `workdays.py` (standard library only) that works on `datetime.date` values
and provides three functions:

    add_months(d: date, months: int) -> date
    business_days_between(start: date, end: date, holidays: Iterable[date] = ()) -> int
    add_business_days(d: date, n: int, holidays: Iterable[date] = ()) -> date

A business day is a date that falls on Monday to Friday and is not in `holidays`.

1. `add_months` returns the date `months` calendar months after `d`; `months` may be negative or
   zero. The day of the month is kept, except that it is clamped to the last day of the target
   month when that month is shorter (Jan 31 plus 1 month is Feb 28, or Feb 29 in a leap year).
   Leap years follow the Gregorian rule (1900 is not a leap year, 2000 is).
2. Every `add_months` result is computed directly from `d`, never by chaining one-month steps:
   Jan 31 plus 2 months is Mar 31, and Feb 29, 2024 plus 12 months is Feb 28, 2025.
3. `business_days_between` counts the business days `x` with `start <= x < end`: `start` is
   included, `end` is excluded, and `start == end` gives 0.
4. If `end` is earlier than `start`, `business_days_between` returns the negative of
   `business_days_between(end, start, holidays)`.
5. `holidays` is any iterable of dates: a list, tuple, set, or a generator that can be read only
   once. A holiday that falls on a Saturday or Sunday has no effect, a date listed more than once
   counts once, and a holiday outside the counted range has no effect. `holidays` behaves the same
   way in `add_business_days`.
6. `add_business_days` returns the date `n` business days after `d` when `n > 0`, and `-n` business
   days before `d` when `n < 0`. `d` itself is never counted, whether or not it is a business day:
   a Friday plus 1 is the next Monday, a Saturday plus 1 is the next Monday, and a Saturday minus 1
   is the Friday before it.
7. With `n == 0`, `add_business_days` returns `d` unchanged, even if `d` is a weekend or a holiday.
8. `d`, `start` and `end` must be `datetime.date` objects. A `datetime.datetime` is not accepted
   even though it is a subclass of `date`. Any such argument that is not a date raises
   `TypeError`, as do a `months` or `n` that is not an `int` (a float, a str or None, for
   example). These errors are raised in every case, including `n == 0` and `start == end`.
