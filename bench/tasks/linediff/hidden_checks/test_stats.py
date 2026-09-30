import random

from linediff import diff, stats


def test_counts_each_op():
    ops = [(" ", "a"), ("-", "b"), ("+", "c"), ("+", "d"), (" ", "e")]
    assert stats(ops) == {"kept": 2, "added": 2, "removed": 1}


def test_empty_diff_is_all_zeros():
    assert stats([]) == {"kept": 0, "added": 0, "removed": 0}


def test_exactly_three_keys_even_when_some_ops_are_missing():
    assert stats([("+", "x")]) == {"kept": 0, "added": 1, "removed": 0}
    assert stats([("-", "x")]) == {"kept": 0, "added": 0, "removed": 1}
    assert set(stats([(" ", "x")])) == {"kept", "added", "removed"}


def test_counts_lines_not_distinct_lines():
    assert stats([("+", "a"), ("+", "a"), ("-", "a"), (" ", "a"), (" ", "a")]) == {
        "kept": 2,
        "added": 2,
        "removed": 1,
    }


def test_stats_of_real_diffs():
    assert stats(diff(["a", "b", "c"], ["a", "x", "c", "d"])) == {
        "kept": 2,
        "added": 2,
        "removed": 1,
    }
    assert stats(diff([], ["a", "b"])) == {"kept": 0, "added": 2, "removed": 0}
    assert stats(diff(["a", "b"], ["a", "b"])) == {"kept": 2, "added": 0, "removed": 0}
    assert stats(diff([], [])) == {"kept": 0, "added": 0, "removed": 0}


def test_stats_agree_with_the_line_counts():
    rng = random.Random(11)
    for _ in range(200):
        old = [rng.choice("abc") for _ in range(rng.randint(0, 9))]
        new = [rng.choice("abc") for _ in range(rng.randint(0, 9))]
        s = stats(diff(old, new))
        assert s["kept"] + s["removed"] == len(old)
        assert s["kept"] + s["added"] == len(new)
