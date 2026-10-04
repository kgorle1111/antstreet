from sudokucheck import conflict_cells

SOLVED = [
    [5, 3, 4, 6, 7, 8, 9, 1, 2],
    [6, 7, 2, 1, 9, 5, 3, 4, 8],
    [1, 9, 8, 3, 4, 2, 5, 6, 7],
    [8, 5, 9, 7, 6, 1, 4, 2, 3],
    [4, 2, 6, 8, 5, 3, 7, 9, 1],
    [7, 1, 3, 9, 2, 4, 8, 5, 6],
    [9, 6, 1, 5, 3, 7, 2, 8, 4],
    [2, 8, 7, 4, 1, 9, 6, 3, 5],
    [3, 4, 5, 2, 8, 6, 1, 7, 9],
]


def grid_with(cells):
    grid = [[0] * 9 for _ in range(9)]
    for (r, c), digit in cells.items():
        grid[r][c] = digit
    return grid


def test_a_pair_in_a_row_marks_both_cells():
    assert conflict_cells(grid_with({(0, 0): 5, (0, 8): 5})) == [(0, 0), (0, 8)]


def test_a_cell_in_a_row_and_a_column_conflict_is_listed_once():
    grid = grid_with({(0, 0): 9, (0, 5): 9, (5, 0): 9})
    assert conflict_cells(grid) == [(0, 0), (0, 5), (5, 0)]


def test_a_box_conflict_marks_both_cells():
    assert conflict_cells(grid_with({(0, 0): 5, (1, 1): 5})) == [(0, 0), (1, 1)]
    assert conflict_cells(grid_with({(7, 7): 2, (8, 6): 2})) == [(7, 7), (8, 6)]


def test_the_result_is_sorted_by_row_then_column():
    grid = grid_with({(0, 0): 1, (0, 1): 1, (0, 8): 2, (8, 8): 2, (4, 4): 3, (4, 5): 3})
    assert conflict_cells(grid) == [(0, 0), (0, 1), (0, 8), (4, 4), (4, 5), (8, 8)]


def test_a_digit_in_three_cells_marks_all_three():
    assert conflict_cells(grid_with({(2, 0): 6, (2, 4): 6, (2, 8): 6})) == [(2, 0), (2, 4), (2, 8)]


def test_cells_with_other_digits_in_the_same_unit_are_not_marked():
    grid = grid_with({(0, 0): 5, (0, 8): 5, (0, 4): 7, (3, 0): 2})
    assert conflict_cells(grid) == [(0, 0), (0, 8)]


def test_empty_cells_are_never_conflicts():
    assert conflict_cells([[0] * 9 for _ in range(9)]) == []
    assert conflict_cells(grid_with({(0, 0): 5})) == []


def test_a_solved_grid_has_no_conflicts_and_a_changed_cell_has_some():
    assert conflict_cells(SOLVED) == []
    bad = [row[:] for row in SOLVED]
    bad[0][0] = 3  # now 3 repeats in row 0 and box 0 (with (0, 1)) and in column 0 (with (8, 0))
    assert conflict_cells(bad) == [(0, 0), (0, 1), (8, 0)]


def test_the_cells_are_plain_int_tuples():
    got = conflict_cells(grid_with({(0, 0): 5, (0, 8): 5}))
    assert all(type(cell) is tuple and len(cell) == 2 for cell in got)
    assert all(type(x) is int for cell in got for x in cell)
