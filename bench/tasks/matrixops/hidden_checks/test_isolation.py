import copy

import pytest
from matrixops import rotate, spiral, transpose

MATRICES = [
    [[1]],
    [[1, 2, 3, 4]],
    [[1], [2], [3], [4]],
    [[1, 2], [3, 4]],
    [[1, 2, 3], [4, 5, 6]],
    [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
]
MATRIX_CALLS = [
    ("rotate0", lambda m: rotate(m, 0)),
    ("rotate1", lambda m: rotate(m)),
    ("rotate2", lambda m: rotate(m, 2)),
    ("rotate3", lambda m: rotate(m, 3)),
    ("rotate-1", lambda m: rotate(m, -1)),
    ("rotate4", lambda m: rotate(m, 4)),
    ("transpose", transpose),
]


@pytest.mark.parametrize("matrix", MATRICES)
@pytest.mark.parametrize("call", [c for _, c in MATRIX_CALLS], ids=[n for n, _ in MATRIX_CALLS])
def test_inputs_are_not_mutated_and_no_rows_are_shared(matrix, call):
    original = copy.deepcopy(matrix)
    input_ids = {id(matrix)} | {id(row) for row in matrix}
    result = call(matrix)
    assert matrix == original
    assert id(result) not in input_ids
    row_ids = [id(row) for row in result]
    assert not set(row_ids) & input_ids
    assert len(set(row_ids)) == len(row_ids)


@pytest.mark.parametrize("matrix", MATRICES)
@pytest.mark.parametrize("call", [c for _, c in MATRIX_CALLS], ids=[n for n, _ in MATRIX_CALLS])
def test_mutating_a_result_leaves_the_input_alone(matrix, call):
    original = copy.deepcopy(matrix)
    result = call(matrix)
    for row in result:
        row[0] = "changed"
        row.append("extra")
    result.append(["extra row"])
    assert matrix == original


@pytest.mark.parametrize("matrix", MATRICES)
def test_spiral_does_not_mutate_and_returns_a_fresh_list(matrix):
    original = copy.deepcopy(matrix)
    result = spiral(matrix)
    assert matrix == original
    assert all(result is not row for row in matrix)
    assert result is not matrix
    result.append("extra")
    result[0] = "changed"
    assert matrix == original
