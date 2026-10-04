import random
from functools import cmp_to_key

from multisort import sort_records


def reference_order(rows, keys):
    """A pairwise comparison written separately from any multi-pass sort."""

    def compare(x, y):
        for spec in keys:
            descending = spec.startswith("-")
            field = spec[1:] if descending else spec
            a, b = x.get(field), y.get(field)
            if a is None and b is None:
                continue
            if a is None:
                return 1
            if b is None:
                return -1
            if a == b:
                continue
            smaller = -1 if a < b else 1
            return -smaller if descending else smaller
        return 0

    return sorted(rows, key=cmp_to_key(compare))  # sorted() is stable


def test_random_records_against_a_pairwise_comparison():
    rng = random.Random(42)
    for _ in range(300):
        rows = []
        for i in range(rng.randint(0, 25)):
            row = {"id": i}
            for field in "abc":
                if rng.random() < 0.8:
                    row[field] = rng.choice([None, 0, 1, 2, 3])
            rows.append(row)
        keys = [rng.choice(["", "-"]) + rng.choice("abc") for _ in range(rng.randint(0, 3))]
        got = sort_records(rows, keys)
        assert [r["id"] for r in got] == [r["id"] for r in reference_order(rows, keys)], keys


def test_random_string_keys():
    rng = random.Random(8)
    words = ["", "a", "B", "b", "ab", "zz", "Zz"]
    for _ in range(100):
        rows = [{"id": i, "w": rng.choice(words), "n": rng.randint(0, 2)} for i in range(15)]
        for keys in (["w"], ["-w", "n"], ["n", "-w"]):
            got = sort_records(rows, keys)
            assert [r["id"] for r in got] == [r["id"] for r in reference_order(rows, keys)]


def test_a_larger_list():
    rng = random.Random(1)
    rows = [{"id": i, "g": rng.randint(0, 20), "v": rng.random()} for i in range(5000)]
    got = sort_records(rows, ["g", "-v"])
    assert [r["id"] for r in got] == [r["id"] for r in reference_order(rows, ["g", "-v"])]
