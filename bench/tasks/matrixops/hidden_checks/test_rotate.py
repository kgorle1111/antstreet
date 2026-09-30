from matrixops import rotate


def test_default_is_one_clockwise_turn_of_a_square():
    assert rotate([[1, 2], [3, 4]]) == [[3, 1], [4, 2]]
    assert rotate([[1, 2, 3], [4, 5, 6], [7, 8, 9]]) == [[7, 4, 1], [8, 5, 2], [9, 6, 3]]


def test_wide_matrix_becomes_tall():
    assert rotate([[1, 2, 3], [4, 5, 6]]) == [[4, 1], [5, 2], [6, 3]]
    assert rotate([[1, 2, 3, 4]]) == [[1], [2], [3], [4]]


def test_tall_matrix_becomes_wide():
    assert rotate([[1, 2], [3, 4], [5, 6]]) == [[5, 3, 1], [6, 4, 2]]
    assert rotate([[1], [2], [3]]) == [[3, 2, 1]]


def test_explicit_turns_argument():
    m = [[1, 2, 3], [4, 5, 6]]
    assert rotate(m, 1) == [[4, 1], [5, 2], [6, 3]]
    assert rotate(m, turns=1) == [[4, 1], [5, 2], [6, 3]]
    assert rotate(m, turns=2) == [[6, 5, 4], [3, 2, 1]]
    assert rotate(m, turns=3) == [[3, 6], [2, 5], [1, 4]]


def test_single_element():
    assert rotate([[9]]) == [[9]]
    assert rotate([[9]], turns=3) == [[9]]
