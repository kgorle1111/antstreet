import pytest
from matrixops import rotate, spiral, transpose

RAGGED = [
    [[1, 2], [3]],
    [[1], [2, 3]],
    [[1, 2, 3], [4, 5], [6, 7, 8]],
    [[1, 2], [3, 4], [5]],
    [[1, 2], [3, 4], [5, 6, 7]],
    [[], [1]],
    [[1], []],
    [[1, 2], [], [3, 4]],
]


@pytest.mark.parametrize("matrix", RAGGED)
def test_spiral_rejects_ragged_rows(matrix):
    with pytest.raises(ValueError):
        spiral(matrix)


@pytest.mark.parametrize("matrix", RAGGED)
def test_transpose_rejects_ragged_rows(matrix):
    with pytest.raises(ValueError):
        transpose(matrix)


@pytest.mark.parametrize("matrix", RAGGED)
@pytest.mark.parametrize("turns", [1, 0, 2, 3, 4, -1, 8])
def test_rotate_rejects_ragged_rows_for_every_turn_count(matrix, turns):
    with pytest.raises(ValueError):
        rotate(matrix, turns)


@pytest.mark.parametrize("matrix", RAGGED)
def test_default_rotate_rejects_ragged_rows(matrix):
    with pytest.raises(ValueError):
        rotate(matrix)
