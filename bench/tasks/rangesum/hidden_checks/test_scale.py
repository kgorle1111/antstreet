import random

from rangesum import RangeSum


def test_a_hundred_thousand_values_with_fifty_thousand_operations():
    rng = random.Random(5)
    n = 100_000
    model = [rng.randint(-1000, 1000) for _ in range(n)]
    rs = RangeSum(list(model))
    assert len(rs) == n
    for step in range(50_000):
        if step % 2 == 0:
            i = rng.randrange(n)
            delta = rng.randint(-50, 50)
            rs.update(i, delta)
            model[i] += delta
        else:
            lo = rng.randrange(n + 1)
            hi = rng.randrange(lo, n + 1)
            got = rs.range_sum(lo, hi)
            if step % 5000 == 1:
                assert got == sum(model[lo:hi])
    assert rs.prefix(n) == sum(model)
    assert rs.range_sum(0, n // 2) == sum(model[: n // 2])
    assert rs.get(n - 1) == model[-1]
