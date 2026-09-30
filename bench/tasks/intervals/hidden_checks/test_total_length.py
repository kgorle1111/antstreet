from intervals import total_length


def test_empty_input_is_zero():
    assert total_length([]) == 0


def test_disjoint_intervals_add_up():
    assert total_length([(0, 3), (10, 15)]) == 8
    assert total_length([(1, 2)]) == 1


def test_overlap_is_counted_once():
    assert total_length([(0, 5), (3, 8)]) == 8
    assert total_length([(0, 10), (2, 4), (5, 6)]) == 10
    assert total_length([(0, 4), (0, 4), (0, 4)]) == 4


def test_touching_intervals_add_up_without_double_counting():
    assert total_length([(0, 3), (3, 6)]) == 6


def test_unsorted_input():
    assert total_length([(10, 12), (0, 3), (2, 5)]) == 7


def test_empty_intervals_count_for_nothing():
    assert total_length([(5, 5)]) == 0
    assert total_length([(1, 1), (0, 2)]) == 2


def test_negative_values():
    assert total_length([(-5, 5)]) == 10
    assert total_length([(-3, -1), (-2, 1)]) == 4
