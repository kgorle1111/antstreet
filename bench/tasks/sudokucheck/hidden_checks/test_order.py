from sudokucheck import violations


def grid_with(cells):
    grid = [[0] * 9 for _ in range(9)]
    for (r, c), digit in cells.items():
        grid[r][c] = digit
    return grid


def test_rows_then_columns_then_boxes_whatever_the_index():
    grid = grid_with(
        {
            (0, 0): 1,
            (0, 1): 1,  # row 0 and box 0, digit 1
            (0, 8): 2,
            (8, 8): 2,  # column 8, digit 2
            (4, 4): 3,
            (4, 5): 3,  # row 4 and box 4, digit 3
        }
    )
    assert violations(grid) == [
        ("row", 0, 1),
        ("row", 4, 3),
        ("col", 8, 2),
        ("box", 0, 1),
        ("box", 4, 3),
    ]


def test_inside_a_kind_the_index_comes_before_the_digit():
    grid = grid_with(
        {
            (1, 0): 9,
            (1, 8): 9,  # row 1, digit 9
            (2, 3): 1,
            (2, 5): 1,  # row 2, digit 1, and box 1 because columns 3 and 5 share it
        }
    )
    assert violations(grid) == [("row", 1, 9), ("row", 2, 1), ("box", 1, 1)]


def test_inside_an_index_digits_ascend():
    grid = grid_with({(6, 0): 8, (6, 3): 8, (6, 1): 1, (6, 7): 1, (6, 2): 5, (6, 8): 5})
    assert violations(grid) == [("row", 6, 1), ("row", 6, 5), ("row", 6, 8)]


def test_columns_sort_by_column_number_then_digit():
    grid = grid_with({(0, 7): 2, (8, 7): 2, (0, 1): 9, (8, 1): 9, (4, 1): 3, (5, 1): 3})
    assert violations(grid) == [("col", 1, 3), ("col", 1, 9), ("col", 7, 2), ("box", 3, 3)]


def test_results_are_plain_tuples_of_str_int_int():
    found = violations(grid_with({(0, 0): 5, (0, 8): 5}))
    assert isinstance(found, list)
    kind, index, digit = found[0]
    assert type(found[0]) is tuple
    assert type(kind) is str and type(index) is int and type(digit) is int
