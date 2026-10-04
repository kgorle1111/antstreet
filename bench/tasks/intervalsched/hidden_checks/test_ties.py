from intervalsched import select_max


def test_equal_ends_the_lower_position_goes_first():
    assert select_max([(0, 2), (1, 2)]) == [0]
    assert select_max([(1, 2), (0, 2)]) == [0]
    assert select_max([(0, 5), (4, 5), (2, 5)]) == [0]


def test_equal_intervals_take_the_first():
    assert select_max([(1, 2), (1, 2)]) == [0]
    assert select_max([(1, 2), (1, 2), (1, 2)]) == [0]
    assert select_max([(3, 4), (1, 2), (1, 2)]) == [1, 0]


def test_a_later_position_wins_only_when_it_ends_earlier():
    assert select_max([(0, 4), (3, 4), (0, 3), (3, 5)]) == [2, 1]
    assert select_max([(0, 3), (0, 4), (3, 4), (3, 5)]) == [0, 2]


def test_which_of_two_equal_ends_is_taken_first_decides_the_rest():
    assert select_max([(5, 8), (0, 4), (4, 8), (8, 9)]) == [1, 0, 3]
    assert select_max([(4, 8), (0, 4), (5, 8), (8, 9)]) == [1, 0, 3]
    assert select_max([(2, 8), (0, 4), (4, 8), (8, 9)]) == [1, 2, 3]
    assert select_max([(4, 8), (0, 4), (2, 8), (8, 9)]) == [1, 0, 3]


def test_equal_ends_with_different_starts_follow_position_not_length():
    assert select_max([(0, 2), (3, 6), (5, 6), (6, 7)]) == [0, 1, 3]
    assert select_max([(0, 2), (5, 6), (3, 6), (6, 7)]) == [0, 1, 3]
