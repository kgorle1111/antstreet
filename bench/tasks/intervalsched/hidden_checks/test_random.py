import random
from itertools import combinations

from intervalsched import max_overlap, select_max


def overlaps(a, b):
    return a[0] < b[1] and b[0] < a[1]


def best_size(rows):
    """Largest set of pairwise non-overlapping intervals, by trying every subset."""
    for size in range(len(rows), 0, -1):
        for combo in combinations(rows, size):
            if not any(overlaps(a, b) for a, b in combinations(combo, 2)):
                return size
    return 0


def best_depth(rows):
    times = {t for row in rows for t in row}
    return max((sum(s <= t < e for s, e in rows) for t in times), default=0)


def make(rng, n):
    rows = []
    for _ in range(n):
        start = rng.randint(0, 12)
        rows.append((start, start + rng.randint(1, 5)))
    return rows


def test_the_selection_is_a_largest_set_of_non_overlapping_intervals():
    rng = random.Random(21)
    for _ in range(250):
        rows = make(rng, rng.randint(0, 9))
        picked = select_max(rows)
        chosen = [rows[i] for i in picked]
        assert len(set(picked)) == len(picked)
        assert not any(overlaps(a, b) for a, b in combinations(chosen, 2))
        assert [c[0] for c in chosen] == sorted(c[0] for c in chosen)
        assert len(picked) == best_size(rows), rows


def test_the_selection_follows_the_stated_order():
    rng = random.Random(4)
    for _ in range(300):
        rows = make(rng, rng.randint(0, 12))
        expected, last_end = [], None
        for i in sorted(range(len(rows)), key=lambda i: (rows[i][1], i)):
            if last_end is None or rows[i][0] >= last_end:
                expected.append(i)
                last_end = rows[i][1]
        assert select_max(rows) == expected, rows


def test_max_overlap_matches_counting_at_every_time():
    rng = random.Random(9)
    for _ in range(300):
        rows = make(rng, rng.randint(0, 12))
        assert max_overlap(rows) == best_depth(rows), rows


def test_float_ends():
    rng = random.Random(17)
    for _ in range(100):
        rows = []
        for _ in range(rng.randint(0, 8)):
            start = rng.randint(0, 20) / 4
            rows.append((start, start + rng.randint(1, 8) / 4))
        picked = select_max(rows)
        assert len(picked) == best_size(rows), rows
        assert max_overlap(rows) == best_depth(rows), rows
