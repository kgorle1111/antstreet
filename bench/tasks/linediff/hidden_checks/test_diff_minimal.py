import random

import pytest
from linediff import diff


def lcs_len(a, b):
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b):
            cur.append(prev[j] + 1 if x == y else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1]


def check(old, new, expected_kept):
    ops = diff(old, new)
    assert [line for op, line in ops if op != "+"] == old
    assert [line for op, line in ops if op != "-"] == new
    assert sum(1 for op, _ in ops if op == " ") == expected_kept


@pytest.mark.parametrize(
    ("old", "new", "kept"),
    [
        (list("XMJYAUZ"), list("MZJAWXU"), 4),
        (["x", "a", "b", "c"], ["a", "b", "c", "x"], 3),
        (["a", "b", "c", "d", "e", "f"], ["f", "e", "d", "c", "b", "a"], 1),
        (["a"] * 5 + ["b"], ["b"] + ["a"] * 5, 5),
        (["a", "b", "a", "c"], ["b", "a", "c", "a"], 3),
        (["a", "x", "b", "y", "c"], ["y", "a", "b", "x", "c"], 3),
        (["a", "b", "c"], ["c", "a", "b"], 2),
        (["a", "a", "b", "b"], ["b", "b", "a", "a"], 2),
    ],
)
def test_kept_count_is_the_longest_common_subsequence(old, new, kept):
    assert lcs_len(old, new) == kept
    check(old, new, kept)


def test_not_just_common_prefix_and_suffix():
    old = ["h", "1", "2", "3", "t"]
    new = ["h", "3", "1", "2", "t"]
    check(old, new, 4)


def test_random_pairs_match_the_lcs_length():
    rng = random.Random(20240601)
    for _ in range(300):
        old = [rng.choice("abc") for _ in range(rng.randint(0, 9))]
        new = [rng.choice("abc") for _ in range(rng.randint(0, 9))]
        check(old, new, lcs_len(old, new))


def test_random_pairs_over_a_wider_alphabet():
    rng = random.Random(99)
    for _ in range(200):
        old = [rng.choice("abcdefgh") for _ in range(rng.randint(0, 12))]
        new = [rng.choice("abcdefgh") for _ in range(rng.randint(0, 12))]
        check(old, new, lcs_len(old, new))
