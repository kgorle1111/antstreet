import random

from editdistance import edit_distance, edit_script


def test_a_few_hundred_characters_each():
    rng = random.Random(1)
    a = "".join(rng.choice("abcd") for _ in range(400))
    b = "".join(rng.choice("abcd") for _ in range(380))
    d = edit_distance(a, b)
    script = edit_script(a, b)
    assert sum(op[0] != "keep" for op in script) == d
    assert abs(len(a) - len(b)) <= d <= 400


def test_long_identical_and_long_disjoint_strings():
    a = "x" * 500
    assert edit_distance(a, a) == 0
    assert edit_script(a, a) == [("keep", "x")] * 500
    assert edit_distance(a, "y" * 500) == 500
    assert edit_distance(a, "") == 500
