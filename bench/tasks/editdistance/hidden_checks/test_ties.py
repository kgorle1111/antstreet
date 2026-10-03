import random
from functools import cache

from editdistance import edit_script

ORDER = {"keep": 0, "sub": 1, "delete": 2, "insert": 3}


def best_script(a, b):
    """Every cheapest script by brute force, then the smallest by the stated order."""

    @cache
    def all_cheapest(i, j):
        if i == len(a) and j == len(b):
            return 0, [()]
        options = []
        if i < len(a) and j < len(b):
            if a[i] == b[j]:
                options.append((0, ("keep", a[i]), i + 1, j + 1))
            else:
                options.append((1, ("sub", a[i], b[j]), i + 1, j + 1))
        if i < len(a):
            options.append((1, ("delete", a[i]), i + 1, j))
        if j < len(b):
            options.append((1, ("insert", b[j]), i, j + 1))
        scored = []
        for cost, op, ni, nj in options:
            rest_cost, rests = all_cheapest(ni, nj)
            scored.append((cost + rest_cost, op, rests))
        best = min(s[0] for s in scored)
        return best, [(op, *rest) for c, op, rests in scored if c == best for rest in rests]

    _, scripts = all_cheapest(0, 0)
    return list(min(scripts, key=lambda s: [ORDER[op[0]] for op in s]))


def test_ties_from_the_idea():
    assert edit_script("ab", "ba") == [("sub", "a", "b"), ("sub", "b", "a")]
    assert edit_script("aab", "ab") == [("keep", "a"), ("delete", "a"), ("keep", "b")]
    assert edit_script("ab", "aab") == [("keep", "a"), ("insert", "a"), ("keep", "b")]
    assert edit_script("flaw", "lawn") == [
        ("delete", "f"),
        ("keep", "l"),
        ("keep", "a"),
        ("keep", "w"),
        ("insert", "n"),
    ]


def test_substitution_beats_a_delete_and_insert_pair():
    assert edit_script("ab", "cd") == [("sub", "a", "c"), ("sub", "b", "d")]
    assert edit_script("abc", "xbz") == [("sub", "a", "x"), ("keep", "b"), ("sub", "c", "z")]


def test_a_run_of_equal_characters_is_kept_from_the_left():
    assert edit_script("aaa", "a") == [("keep", "a"), ("delete", "a"), ("delete", "a")]
    assert edit_script("a", "aaa") == [("keep", "a"), ("insert", "a"), ("insert", "a")]


def test_keep_wins_over_sub_when_both_are_cheapest():
    assert edit_script("abab", "ab") == [
        ("keep", "a"),
        ("keep", "b"),
        ("delete", "a"),
        ("delete", "b"),
    ]


def test_matches_a_brute_force_search_on_small_strings():
    rng = random.Random(5)
    for _ in range(400):
        a = "".join(rng.choice("ab") for _ in range(rng.randint(0, 7)))
        b = "".join(rng.choice("ab") for _ in range(rng.randint(0, 7)))
        assert edit_script(a, b) == best_script(a, b), (a, b)
    for _ in range(200):
        a = "".join(rng.choice("abc") for _ in range(rng.randint(0, 6)))
        b = "".join(rng.choice("abc") for _ in range(rng.randint(0, 6)))
        assert edit_script(a, b) == best_script(a, b), (a, b)
