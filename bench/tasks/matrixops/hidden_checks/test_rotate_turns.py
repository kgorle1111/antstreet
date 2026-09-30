import pytest
from matrixops import rotate

M = [[1, 2, 3], [4, 5, 6]]
BY_QUARTER_TURNS = [
    [[1, 2, 3], [4, 5, 6]],
    [[4, 1], [5, 2], [6, 3]],
    [[6, 5, 4], [3, 2, 1]],
    [[3, 6], [2, 5], [1, 4]],
]


@pytest.mark.parametrize("turns", range(-9, 10))
def test_turns_are_taken_modulo_4(turns):
    assert rotate(M, turns) == BY_QUARTER_TURNS[turns % 4]


@pytest.mark.parametrize("turns", [0, 4, 8, -4, -400])
def test_multiples_of_four_return_an_equal_matrix(turns):
    assert rotate(M, turns) == M


def test_negative_turns_go_counter_clockwise():
    assert rotate([[1, 2], [3, 4]], -1) == [[2, 4], [1, 3]]
    assert rotate([[1, 2, 3], [4, 5, 6]], -1) == [[3, 6], [2, 5], [1, 4]]


@pytest.mark.parametrize("turns", [10**18 + 3, -(10**18) - 1, 2**64 + 2])
def test_huge_turn_counts_finish_immediately(turns):
    assert rotate(M, turns) == BY_QUARTER_TURNS[turns % 4]
