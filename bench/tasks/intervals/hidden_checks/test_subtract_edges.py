from intervals import subtract


def test_subtracting_nothing_merges_a():
    assert subtract([(5, 8), (1, 3), (2, 4)], []) == [(1, 4), (5, 8)]


def test_subtracting_from_nothing_gives_nothing():
    assert subtract([], [(1, 5)]) == []
    assert subtract([], []) == []


def test_result_is_merged_even_when_a_is_split_in_pieces():
    assert subtract([(0, 5), (5, 10)], [(3, 4)]) == [(0, 3), (4, 10)]
    assert subtract([(0, 6), (4, 10)], [(20, 30)]) == [(0, 10)]


def test_unsorted_overlapping_holes():
    assert subtract([(0, 20)], [(12, 15), (2, 6), (5, 9), (8, 10)]) == [
        (0, 2),
        (10, 12),
        (15, 20),
    ]


def test_touching_holes_leave_no_sliver():
    assert subtract([(0, 10)], [(2, 4), (4, 6)]) == [(0, 2), (6, 10)]


def test_empty_intervals_are_ignored():
    assert subtract([(3, 3), (0, 10)], [(5, 5)]) == [(0, 10)]
    assert subtract([(4, 4)], [(0, 10)]) == []
    assert subtract([(0, 5)], [(2, 2)]) == [(0, 5)]


def test_negative_values():
    assert subtract([(-10, 10)], [(-3, 3)]) == [(-10, -3), (3, 10)]
    assert subtract([(-10, -5)], [(-8, -6)]) == [(-10, -8), (-6, -5)]


def test_subtracting_a_set_from_itself_gives_nothing():
    data = [(0, 4), (3, 9), (12, 15)]
    assert subtract(data, data) == []
