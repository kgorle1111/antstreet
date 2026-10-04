import random

from intervalsched import max_overlap, select_max


def test_a_hundred_thousand_back_to_back_intervals():
    n = 100_000
    rows = [(i, i + 1) for i in range(n)]
    assert select_max(rows) == list(range(n))
    assert max_overlap(rows) == 1


def test_a_hundred_thousand_random_intervals():
    rng = random.Random(5)
    rows = []
    for _ in range(100_000):
        start = rng.randint(0, 1_000_000)
        rows.append((start, start + rng.randint(1, 50)))
    picked = select_max(rows)
    chosen = [rows[i] for i in picked]
    assert all(a[1] <= b[0] for a, b in zip(chosen, chosen[1:], strict=False))
    assert len(picked) > 1000
    assert max_overlap(rows) >= 2


def test_a_hundred_thousand_nested_intervals():
    n = 100_000
    rows = [(-i, i + 1) for i in range(n)]
    assert max_overlap(rows) == n
    assert select_max(rows) == [0]
