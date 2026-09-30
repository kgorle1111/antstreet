from matrixops import transpose


def test_square():
    assert transpose([[1, 2], [3, 4]]) == [[1, 3], [2, 4]]
    assert transpose([[1, 2, 3], [4, 5, 6], [7, 8, 9]]) == [[1, 4, 7], [2, 5, 8], [3, 6, 9]]


def test_rectangles_change_shape():
    assert transpose([[1, 2, 3], [4, 5, 6]]) == [[1, 4], [2, 5], [3, 6]]
    assert transpose([[1, 2], [3, 4], [5, 6]]) == [[1, 3, 5], [2, 4, 6]]


def test_row_becomes_column_and_back():
    assert transpose([[1, 2, 3]]) == [[1], [2], [3]]
    assert transpose([[1], [2], [3]]) == [[1, 2, 3]]


def test_single_element():
    assert transpose([[5]]) == [[5]]


def test_rows_are_lists():
    result = transpose([[1, 2, 3], [4, 5, 6]])
    assert isinstance(result, list)
    assert all(isinstance(row, list) for row in result)


def test_transposing_twice_restores_every_shape():
    for rows in range(1, 6):
        for cols in range(1, 6):
            m = [[r * 10 + c for c in range(cols)] for r in range(rows)]
            assert transpose(transpose(m)) == m
            assert len(transpose(m)) == cols
