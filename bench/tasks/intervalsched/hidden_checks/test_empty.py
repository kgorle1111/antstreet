import copy

from intervalsched import max_overlap, select_max


def test_empty_input():
    assert select_max([]) == []
    assert max_overlap([]) == 0
    assert select_max(()) == []


def test_pairs_may_be_lists_or_tuples_and_a_tuple_of_them_is_fine():
    assert select_max([[1, 2], [2, 3]]) == [0, 1]
    assert select_max(((1, 2), (2, 3))) == [0, 1]
    assert max_overlap(([1, 4], [2, 3])) == 2


def test_the_argument_is_not_changed():
    rows = [(5, 9), (1, 4), (3, 8), (1, 4)]
    before = copy.deepcopy(rows)
    select_max(rows)
    max_overlap(rows)
    assert rows == before
