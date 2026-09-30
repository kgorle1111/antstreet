from intervals import merge


def test_empty_intervals_are_dropped():
    assert merge([(5, 5)]) == []
    assert merge([(1, 1), (7, 7), (-3, -3)]) == []


def test_empty_interval_among_real_ones_is_dropped():
    assert merge([(1, 3), (4, 4), (6, 8)]) == [(1, 3), (6, 8)]
    assert merge([(0, 0), (2, 4)]) == [(2, 4)]


def test_empty_interval_never_bridges_a_gap():
    assert merge([(1, 2), (3, 3), (4, 5)]) == [(1, 2), (4, 5)]
    assert merge([(1, 2), (2, 2), (3, 4)]) == [(1, 2), (3, 4)]


def test_empty_interval_inside_or_touching_a_real_one_changes_nothing():
    assert merge([(1, 6), (3, 3)]) == [(1, 6)]
    assert merge([(1, 3), (3, 3)]) == [(1, 3)]
    assert merge([(3, 3), (3, 5)]) == [(3, 5)]
