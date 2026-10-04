from intervalsched import max_overlap


def test_examples_from_the_idea():
    assert max_overlap([(1, 3), (3, 5)]) == 1
    assert max_overlap([(1, 4), (2, 5), (3, 6)]) == 3
    assert max_overlap([(1, 5), (2, 3), (2, 3)]) == 3


def test_empty_and_single():
    assert max_overlap([]) == 0
    assert max_overlap([(4, 5)]) == 1


def test_disjoint_nested_and_chained():
    assert max_overlap([(1, 2), (3, 4), (5, 6)]) == 1
    assert max_overlap([(0, 10), (1, 9), (2, 8), (3, 7)]) == 4
    assert max_overlap([(0, 2), (1, 3), (2, 4), (3, 5)]) == 2


def test_the_peak_is_not_at_the_start_or_the_end():
    assert max_overlap([(0, 10), (4, 6), (5, 7), (5, 5.5), (20, 30)]) == 4


def test_negative_and_float_times():
    assert max_overlap([(-3, -1), (-2, 0.5), (-1.5, -1.25)]) == 3
    assert max_overlap([(0.1, 0.2), (0.2, 0.3), (0.15, 0.25)]) == 2


def test_equal_intervals_all_count():
    assert max_overlap([(1, 2)] * 7) == 7


def test_input_order_does_not_matter():
    rows = [(5, 9), (1, 4), (3, 8), (2, 6), (7, 10), (0, 1)]
    expected = max_overlap(rows)
    assert expected == 3
    assert max_overlap(rows[::-1]) == expected
    assert max_overlap(sorted(rows)) == expected
