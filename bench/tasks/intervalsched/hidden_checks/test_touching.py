from intervalsched import max_overlap, select_max


def test_intervals_that_touch_do_not_overlap():
    assert select_max([(1, 3), (3, 5)]) == [0, 1]
    assert select_max([(3, 5), (1, 3)]) == [1, 0]
    assert select_max([(1, 2), (2, 3), (3, 4), (4, 5)]) == [0, 1, 2, 3]


def test_intervals_that_share_a_sliver_do_overlap():
    assert select_max([(1, 3), (2.999, 5)]) == [0]
    assert select_max([(1, 3), (2, 5)]) == [0]


def test_touching_ends_do_not_add_to_the_overlap_count():
    assert max_overlap([(1, 3), (3, 5)]) == 1
    assert max_overlap([(1, 2), (2, 3), (3, 4)]) == 1
    assert max_overlap([(0, 2), (2, 4), (1, 3)]) == 2


def test_many_intervals_touching_at_one_time():
    assert max_overlap([(0, 5), (1, 5), (2, 5), (5, 9), (5, 8)]) == 3
    assert max_overlap([(5, 9), (5, 8), (0, 5)]) == 2
