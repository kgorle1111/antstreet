Interval = tuple[int, int]


def merge(intervals: list[Interval]) -> list[Interval]:
    pending: list[Interval] = []
    for start, end in intervals:
        if start > end:
            raise ValueError(f"invalid interval ({start}, {end}): start > end")
        if start < end:
            pending.append((start, end))
    merged: list[Interval] = []
    for start, end in sorted(pending):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def subtract(a: list[Interval], b: list[Interval]) -> list[Interval]:
    holes = merge(b)
    result: list[Interval] = []
    for start, end in merge(a):
        cursor = start
        for hole_start, hole_end in holes:
            if hole_end <= cursor:
                continue
            if hole_start >= end:
                break
            if hole_start > cursor:
                result.append((cursor, hole_start))
            cursor = hole_end
        if cursor < end:
            result.append((cursor, end))
    return result


def total_length(intervals: list[Interval]) -> int:
    return sum(end - start for start, end in merge(intervals))
