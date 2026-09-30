import random

from linediff import apply, diff


def test_apply_hand_built_diffs():
    assert apply([], []) == []
    assert apply([], [("+", "x")]) == ["x"]
    assert apply(["a", "b"], [(" ", "a"), ("-", "b"), ("+", "c")]) == ["a", "c"]
    assert apply(["a", "b"], [("-", "a"), ("-", "b")]) == []
    assert apply(["a", "b"], [(" ", "a"), (" ", "b")]) == ["a", "b"]


def test_ops_need_not_be_in_the_order_diff_produces():
    assert apply(["a"], [("+", "x"), ("-", "a")]) == ["x"]
    assert apply(["a", "b"], [("+", "x"), (" ", "a"), ("+", "y"), (" ", "b"), ("+", "z")]) == [
        "x",
        "a",
        "y",
        "b",
        "z",
    ]


def test_ops_need_not_be_minimal():
    assert apply(["a", "a"], [("-", "a"), ("+", "a"), (" ", "a")]) == ["a", "a"]


def test_round_trip_on_examples():
    cases = [
        ([], []),
        (["a"], []),
        ([], ["a"]),
        (["a", "b", "c"], ["c", "b", "a"]),
        (["x", "", "y"], ["", "y", "x"]),
        (["a", "a", "b"], ["a", "b", "a"]),
    ]
    for old, new in cases:
        assert apply(old, diff(old, new)) == new


def test_round_trip_on_random_pairs():
    rng = random.Random(5)
    for _ in range(300):
        old = [rng.choice("abc") for _ in range(rng.randint(0, 10))]
        new = [rng.choice("abc") for _ in range(rng.randint(0, 10))]
        assert apply(old, diff(old, new)) == new


def test_old_is_not_modified_and_result_is_a_new_list():
    old = ["a", "b"]
    result = apply(old, [(" ", "a"), (" ", "b")])
    assert old == ["a", "b"]
    assert result == old
    assert result is not old
    result.append("c")
    assert old == ["a", "b"]
    assert isinstance(apply(old, [(" ", "a"), ("-", "b")]), list)
