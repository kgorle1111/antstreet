# select_max treats intervals that touch at one time as overlapping, so (1, 3) and (3, 5) clash.
def _validate(intervals: object) -> list[tuple[float, float]]:
    if not isinstance(intervals, list | tuple):
        raise TypeError("intervals must be a list")
    checked = []
    for item in intervals:
        if not isinstance(item, list | tuple) or len(item) != 2:
            raise ValueError(f"an interval must be a (start, end) pair, got {item!r}")
        for value in item:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise TypeError(f"interval ends must be numbers, got {value!r}")
        start, end = item
        if not start < end:
            raise ValueError(f"an interval must start before it ends, got {item!r}")
        checked.append((start, end))
    return checked


def select_max(intervals: list[tuple[float, float]]) -> list[int]:
    checked = _validate(intervals)
    chosen: list[int] = []
    last_end = None
    for i in sorted(range(len(checked)), key=lambda i: (checked[i][1], i)):
        start, end = checked[i]
        if last_end is None or start > last_end:
            chosen.append(i)
            last_end = end
    return chosen


def max_overlap(intervals: list[tuple[float, float]]) -> int:
    checked = _validate(intervals)
    events = [(start, 1) for start, _ in checked] + [(end, -1) for _, end in checked]
    events.sort()  # at equal times an end (-1) sorts before a start (+1): touching is not overlap
    best = depth = 0
    for _, delta in events:
        depth += delta
        best = max(best, depth)
    return best
