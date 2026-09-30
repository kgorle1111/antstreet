import pytest
from matrixops import rotate, spiral, transpose

EMPTIES = [[], [[]], [[], []], [[], [], []]]


@pytest.mark.parametrize("matrix", EMPTIES)
def test_spiral_of_empty_is_empty_list(matrix):
    result = spiral(matrix)
    assert isinstance(result, list)
    assert result == []


@pytest.mark.parametrize("matrix", EMPTIES)
def test_transpose_of_empty_is_empty_list(matrix):
    result = transpose(matrix)
    assert isinstance(result, list)
    assert result == []


@pytest.mark.parametrize("matrix", EMPTIES)
@pytest.mark.parametrize("turns", [1, 0, 2, 3, 4, -1, -6])
def test_rotate_of_empty_is_empty_list_for_every_turn_count(matrix, turns):
    result = rotate(matrix, turns)
    assert isinstance(result, list)
    assert result == []


@pytest.mark.parametrize("matrix", EMPTIES)
def test_default_rotate_of_empty(matrix):
    assert rotate(matrix) == []
