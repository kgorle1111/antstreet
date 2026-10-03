from intervalsched import select_max


def test_the_classic_example():
    assert select_max([(1, 4), (3, 5), (0, 6), (5, 7), (3, 9), (5, 9)]) == [0, 3]


def test_disjoint_intervals_are_all_taken_in_time_order():
    assert select_max([(5, 6), (1, 2), (3, 4)]) == [1, 2, 0]


def test_a_long_interval_loses_to_the_short_ones_inside_it():
    assert select_max([(0, 10), (1, 2), (3, 4), (5, 6)]) == [1, 2, 3]


def test_the_one_that_ends_first_wins_not_the_one_that_starts_first():
    assert select_max([(0, 5), (1, 2), (3, 4)]) == [1, 2]
    assert select_max([(0, 3), (1, 2), (2, 5)]) == [1, 2]


def test_not_the_shortest_first():
    # taking the shortest interval (4, 5) would block both of the others
    assert select_max([(0, 4), (4, 5), (5, 9)]) == [0, 1, 2]
    assert select_max([(1, 3), (2, 3.5), (3, 6), (5, 7)]) == [0, 2]


def test_a_single_interval_and_a_chain_of_nested_ones():
    assert select_max([(2, 3)]) == [0]
    assert select_max([(0, 8), (1, 7), (2, 6), (3, 5)]) == [3]


def test_negative_and_float_times():
    assert select_max([(-5, -3), (-4, -1), (-3, 0.5), (0.5, 2.25)]) == [0, 2, 3]
    assert select_max([(0.1, 0.2), (0.15, 0.3), (0.2, 0.4)]) == [0, 2]


def test_the_result_is_a_list_of_plain_ints():
    out = select_max([(1, 2), (2, 3)])
    assert isinstance(out, list) and all(type(i) is int for i in out)
