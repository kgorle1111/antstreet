import random

from linediff import apply, diff, stats


def edited(old, rng, deletions, insertions):
    keep = sorted(rng.sample(range(len(old)), len(old) - deletions))
    new = [old[i] for i in keep]
    for k in range(insertions):
        new.insert(rng.randint(0, len(new)), f"fresh-{k}")
    return new


def test_a_thousand_lines_with_scattered_edits():
    rng = random.Random(1)
    old = [f"line {i % 300}" for i in range(1000)]
    new = edited(old, rng, deletions=60, insertions=60)
    ops = diff(old, new)
    assert [line for op, line in ops if op != "+"] == old
    assert [line for op, line in ops if op != "-"] == new
    assert stats(ops) == {"kept": 940, "added": 60, "removed": 60}
    assert apply(old, ops) == new


def test_two_thousand_lines_with_three_edits():
    old = [f"line {i}" for i in range(2000)]
    new = old[:500] + ["changed"] + old[501:1200] + ["extra"] + old[1200:1900] + old[1901:]
    ops = diff(old, new)
    assert stats(ops) == {"kept": 1998, "added": 2, "removed": 2}
    assert apply(old, ops) == new


def test_two_thousand_identical_lines():
    old = [f"line {i}" for i in range(2000)]
    assert diff(old, list(old)) == [(" ", line) for line in old]


def test_completely_different_lists():
    old = [f"old {i}" for i in range(800)]
    new = [f"new {i}" for i in range(800)]
    assert diff(old, new) == [("-", line) for line in old] + [("+", line) for line in new]


def test_many_repeated_lines():
    old = ["x"] * 500
    new = ["x"] * 700
    ops = diff(old, new)
    assert stats(ops) == {"kept": 500, "added": 200, "removed": 0}
    assert apply(old, ops) == new
