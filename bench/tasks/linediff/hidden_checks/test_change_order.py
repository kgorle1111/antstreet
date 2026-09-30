import random

from linediff import diff


def has_addition_before_removal(ops):
    return any(a[0] == "+" and b[0] == "-" for a, b in zip(ops, ops[1:], strict=False))


def test_no_kept_lines_gives_all_removals_then_all_additions():
    assert diff(["a", "b", "c"], ["x", "y"]) == [
        ("-", "a"),
        ("-", "b"),
        ("-", "c"),
        ("+", "x"),
        ("+", "y"),
    ]


def test_runs_between_kept_lines():
    old = ["k1", "a", "b", "k2", "c"]
    new = ["k1", "x", "k2", "y", "z"]
    assert diff(old, new) == [
        (" ", "k1"),
        ("-", "a"),
        ("-", "b"),
        ("+", "x"),
        (" ", "k2"),
        ("-", "c"),
        ("+", "y"),
        ("+", "z"),
    ]


def test_leading_and_trailing_runs():
    old = ["a", "b", "k", "c"]
    new = ["x", "y", "z", "k", "w"]
    assert diff(old, new) == [
        ("-", "a"),
        ("-", "b"),
        ("+", "x"),
        ("+", "y"),
        ("+", "z"),
        (" ", "k"),
        ("-", "c"),
        ("+", "w"),
    ]


def test_more_removals_than_additions_and_the_reverse():
    assert diff(["a", "b", "c", "k"], ["x", "k"]) == [
        ("-", "a"),
        ("-", "b"),
        ("-", "c"),
        ("+", "x"),
        (" ", "k"),
    ]
    assert diff(["k", "a"], ["k", "x", "y", "z"]) == [
        (" ", "k"),
        ("-", "a"),
        ("+", "x"),
        ("+", "y"),
        ("+", "z"),
    ]


def test_random_pairs_never_add_before_removing_within_a_run():
    rng = random.Random(4242)
    for _ in range(300):
        old = [rng.choice("abcd") for _ in range(rng.randint(0, 10))]
        new = [rng.choice("abcd") for _ in range(rng.randint(0, 10))]
        assert not has_addition_before_removal(diff(old, new)), (old, new)
