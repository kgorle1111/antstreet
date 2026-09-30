from intervals import merge


def test_touching_intervals_are_merged():
    assert merge([(1, 3), (3, 5)]) == [(1, 5)]
    assert merge([(3, 5), (1, 3)]) == [(1, 5)]


def test_chain_of_touching_intervals():
    assert merge([(4, 6), (0, 2), (2, 4), (6, 9)]) == [(0, 9)]


def test_a_gap_of_one_integer_keeps_intervals_apart():
    assert merge([(1, 2), (3, 4)]) == [(1, 2), (3, 4)]
    assert merge([(3, 4), (1, 2)]) == [(1, 2), (3, 4)]


def test_touch_and_gap_mixed():
    assert merge([(1, 3), (3, 5), (6, 8), (8, 9)]) == [(1, 5), (6, 9)]
