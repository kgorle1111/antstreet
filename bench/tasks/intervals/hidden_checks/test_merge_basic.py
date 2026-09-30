from intervals import merge


def test_sorted_disjoint_input_is_unchanged():
    assert merge([(1, 3), (5, 8), (10, 12)]) == [(1, 3), (5, 8), (10, 12)]


def test_overlapping_intervals_are_merged():
    assert merge([(1, 5), (3, 8)]) == [(1, 8)]
    assert merge([(1, 4), (2, 6), (5, 9), (20, 25)]) == [(1, 9), (20, 25)]


def test_unsorted_input_gives_sorted_output():
    assert merge([(10, 12), (1, 3), (5, 8)]) == [(1, 3), (5, 8), (10, 12)]
    assert merge([(6, 9), (1, 4), (3, 7)]) == [(1, 9)]


def test_nested_and_duplicate_intervals():
    assert merge([(1, 10), (2, 3), (4, 5)]) == [(1, 10)]
    assert merge([(2, 3), (1, 10)]) == [(1, 10)]
    assert merge([(4, 6), (4, 6), (4, 6)]) == [(4, 6)]


def test_single_interval_and_empty_list():
    assert merge([(2, 7)]) == [(2, 7)]
    assert merge([]) == []


def test_negative_and_zero_values():
    assert merge([(-5, -1), (-3, 2), (4, 6)]) == [(-5, 2), (4, 6)]
    assert merge([(0, 3), (-2, 0)]) == [(-2, 3)]


def test_result_is_a_list_of_tuples():
    result = merge([(1, 3), (2, 4)])
    assert isinstance(result, list)
    assert all(isinstance(item, tuple) for item in result)
