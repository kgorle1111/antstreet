from matrixops import spiral


def grid(rows, cols):
    return [[r * cols + c + 1 for c in range(cols)] for r in range(rows)]


def oracle(matrix):
    out = []
    while matrix:
        out += matrix[0]
        matrix = [list(col) for col in zip(*matrix[1:], strict=True)][::-1]
    return out


def test_square_matrices():
    assert spiral([[1]]) == [1]
    assert spiral([[1, 2], [3, 4]]) == [1, 2, 4, 3]
    assert spiral([[1, 2, 3], [4, 5, 6], [7, 8, 9]]) == [1, 2, 3, 6, 9, 8, 7, 4, 5]
    assert spiral(grid(4, 4)) == [1, 2, 3, 4, 8, 12, 16, 15, 14, 13, 9, 5, 6, 7, 11, 10]


def test_wide_and_tall_rectangles():
    assert spiral(grid(3, 4)) == [1, 2, 3, 4, 8, 12, 11, 10, 9, 5, 6, 7]
    assert spiral(grid(4, 3)) == [1, 2, 3, 6, 9, 12, 11, 10, 7, 4, 5, 8]
    assert spiral(grid(2, 5)) == [1, 2, 3, 4, 5, 10, 9, 8, 7, 6]
    assert spiral(grid(5, 2)) == [1, 2, 4, 6, 8, 10, 9, 7, 5, 3]


def test_single_row_and_single_column():
    assert spiral([[1, 2, 3, 4]]) == [1, 2, 3, 4]
    assert spiral([[1], [2], [3], [4]]) == [1, 2, 3, 4]
    assert spiral([[7]]) == [7]


def test_every_shape_up_to_7_by_7_matches_an_independent_oracle():
    for rows in range(1, 8):
        for cols in range(1, 8):
            m = grid(rows, cols)
            assert spiral(m) == oracle(m), (rows, cols)
