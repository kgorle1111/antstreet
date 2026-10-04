import copy

from sudokucheck import is_solved, violations

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


def test_a_correct_full_grid_is_solved():
    assert is_solved(SOLVED) is True
    assert violations(SOLVED) == []


def test_an_unfinished_grid_without_repeats_is_not_solved():
    grid = copy.deepcopy(SOLVED)
    grid[4][4] = 0
    assert violations(grid) == []
    assert is_solved(grid) is False


def test_an_empty_grid_is_not_solved():
    assert is_solved([[0] * 9 for _ in range(9)]) is False


def test_a_full_grid_with_a_repeat_is_not_solved():
    grid = copy.deepcopy(SOLVED)
    grid[0][0], grid[0][1] = grid[0][1], grid[0][0]
    assert all(all(row) for row in grid)
    assert is_solved(grid) is False
    assert violations(grid) == [("col", 0, 3), ("col", 1, 5)]


def test_every_single_cell_change_to_a_solved_grid_breaks_it():
    for r in range(9):
        for c in range(9):
            grid = copy.deepcopy(SOLVED)
            grid[r][c] = grid[r][(c + 1) % 9]
            assert is_solved(grid) is False


def test_a_solved_grid_stays_solved_under_row_swaps_in_a_band_and_digit_relabelling():
    grid = copy.deepcopy(SOLVED)
    grid[0], grid[2] = grid[2], grid[0]
    grid[3], grid[4] = grid[4], grid[3]
    assert is_solved(grid) is True
    relabelled = [[10 - v for v in row] for row in SOLVED]
    assert is_solved(relabelled) is True
    transposed = [list(col) for col in zip(*SOLVED, strict=True)]
    assert is_solved(transposed) is True


def test_swapping_two_rows_from_different_bands_breaks_the_boxes():
    grid = copy.deepcopy(SOLVED)
    grid[0], grid[3] = grid[3], grid[0]
    assert is_solved(grid) is False
    assert any(kind == "box" for kind, _, _ in violations(grid))


def test_the_result_is_a_real_bool_and_tuples_are_accepted():
    assert type(is_solved(SOLVED)) is bool
    assert type(is_solved([[0] * 9] * 9)) is bool
    assert is_solved(tuple(tuple(row) for row in SOLVED)) is True
