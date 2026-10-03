Create a Python module `intervalsched.py` (standard library only) with two functions over time
intervals:

    select_max(intervals: list[tuple[float, float]]) -> list[int]
    max_overlap(intervals: list[tuple[float, float]]) -> int

1. An interval is a pair `(start, end)` of ints or floats with `start < end`. It is half-open: it
   covers the times `t` with `start <= t < end`. Two intervals overlap when some time is covered
   by both, so `(1, 3)` and `(3, 5)` do not overlap, and `(1, 3)` and `(2, 4)` do. Intervals may
   be negative, equal to each other, or nested.
2. `select_max(intervals)` picks as many intervals as it can with no two overlapping and returns
   their positions in the input list. The result is built like this: look at the intervals in
   order of `end`, smallest first, and among equal ends the one with the lower position first;
   take an interval when it does not overlap the last one taken (its `start` is at least the
   `end` of the last one taken), skip it otherwise. The positions are returned in the order they
   were taken, which is the order of the times. This always gives a largest possible set.
   For `[(1, 4), (3, 5), (0, 6), (5, 7), (3, 9), (5, 9)]` the result is `[0, 3]`. For
   `[(1, 3), (3, 5)]` it is `[0, 1]`. For `[(0, 2), (1, 2)]` and for `[(1, 2), (0, 2)]` it is
   `[0]`, and for two equal intervals `[(1, 2), (1, 2)]` it is `[0]`. An empty list gives `[]`.
3. `max_overlap(intervals)` is the largest number of intervals that cover one common time, and 0
   for an empty list. `max_overlap([(1, 3), (3, 5)])` is 1, `max_overlap([(1, 4), (2, 5), (3, 6)])`
   is 3 and `max_overlap([(1, 5), (2, 3), (2, 3)])` is 3.
4. Both functions check every interval in the list, including ones that would not be chosen or
   counted. A `intervals` argument that is not a list or tuple raises `TypeError`. An item that is
   not a list or tuple of exactly two values raises `ValueError`. An end that is not an int or
   float (`bool` is not one, nor a string or `None`) raises `TypeError`. A pair with
   `start >= end` (an empty or backwards interval) raises `ValueError`. When one list has several
   problems, the first bad item in list order decides which error is raised, and within an item
   the shape is checked first, then the types, then the order of the two ends.
5. Neither function changes its argument. Lists of 100,000 intervals must be handled in a few
   seconds.
