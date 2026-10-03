import random

from rangesum import RangeSum


def test_random_operations_match_a_plain_list():
    rng = random.Random(9)
    for _ in range(60):
        n = rng.randint(1, 40)
        model = [rng.randint(-20, 20) for _ in range(n)]
        rs = RangeSum(list(model))
        for _ in range(80):
            action = rng.choice(["update", "set", "get", "prefix", "range"])
            if action == "update":
                i, delta = rng.randrange(n), rng.randint(-9, 9)
                rs.update(i, delta)
                model[i] += delta
            elif action == "set":
                i, value = rng.randrange(n), rng.randint(-9, 9)
                rs.set(i, value)
                model[i] = value
            elif action == "get":
                i = rng.randrange(n)
                assert rs.get(i) == model[i]
            elif action == "prefix":
                k = rng.randint(0, n)
                assert rs.prefix(k) == sum(model[:k])
            else:
                lo = rng.randint(0, n)
                hi = rng.randint(lo, n)
                assert rs.range_sum(lo, hi) == sum(model[lo:hi])
        assert [rs.get(i) for i in range(n)] == model
        assert rs.prefix(n) == sum(model)
