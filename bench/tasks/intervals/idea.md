Create a Python module `intervals.py` (standard library only) with three functions over integer intervals:

    merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]
    subtract(a: list[tuple[int, int]], b: list[tuple[int, int]]) -> list[tuple[int, int]]
    total_length(intervals: list[tuple[int, int]]) -> int

1. An interval `(start, end)` is half-open: it covers the integers x with `start <= x < end`.
   `(1, 3)` covers 1 and 2. Values may be negative or zero.
2. An interval with `start == end` is empty and covers nothing. An interval with `start > end` is
   invalid: every function raises `ValueError` if any interval in any of its arguments (including
   `b`, and including intervals that would be redundant or empty) has `start > end`.
3. `merge` returns a new list of `(start, end)` tuples covering exactly the same integers as the
   input, sorted by start, with no empty interval, and with no two intervals overlapping or
   touching. An empty input gives `[]`.
4. Overlapping intervals are merged, and so are touching ones: `(1, 3)` and `(3, 5)` become
   `(1, 5)`. Intervals separated by a gap of at least one uncovered integer stay separate:
   `(1, 2)` and `(3, 4)` stay two intervals, because 2 is not covered.
5. The input of `merge` may be unsorted and may contain overlapping, nested, duplicate and empty
   intervals. Empty intervals are dropped.
6. `subtract(a, b)` returns a new list in exactly the form of rule 3: the intervals covering the
   integers covered by `a` and not covered by `b`. Both arguments may be unsorted, overlapping or
   contain empty intervals. Example: `subtract([(0, 10)], [(3, 5)])` is `[(0, 3), (5, 10)]`.
7. `total_length(intervals)` returns how many integers are covered by at least one interval. An
   integer covered by several intervals is counted once. An empty input gives 0.
8. No function mutates its arguments: the lists passed in keep their contents and their order.
