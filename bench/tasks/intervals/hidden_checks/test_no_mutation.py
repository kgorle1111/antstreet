from intervals import merge, subtract, total_length


def test_merge_leaves_its_argument_alone():
    data = [(10, 12), (1, 3), (2, 6), (5, 5), (12, 14)]
    snapshot = list(data)
    merge(data)
    assert data == snapshot


def test_subtract_leaves_both_arguments_alone():
    a = [(8, 12), (0, 4), (3, 9)]
    b = [(6, 7), (1, 2), (5, 5)]
    a_snapshot, b_snapshot = list(a), list(b)
    subtract(a, b)
    assert a == a_snapshot
    assert b == b_snapshot


def test_total_length_leaves_its_argument_alone():
    data = [(8, 12), (0, 4), (3, 9)]
    snapshot = list(data)
    total_length(data)
    assert data == snapshot


def test_results_are_new_lists():
    data = [(1, 3), (5, 8)]
    assert merge(data) is not data
    assert subtract(data, []) is not data
    merge(data).append((100, 200))
    assert data == [(1, 3), (5, 8)]
