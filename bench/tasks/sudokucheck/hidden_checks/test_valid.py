import copy

from sudokucheck import conflict_cells, is_solved, violations

PUZZLE = [
    [5, 3, 0, 0, 7, 0, 0, 0, 0],
    [6, 0, 0, 1, 9, 5, 0, 0, 0],
    [0, 9, 8, 0, 0, 0, 0, 6, 0],
    [8, 0, 0, 0, 6, 0, 0, 0, 3],
    [4, 0, 0, 8, 0, 3, 0, 0, 1],
    [7, 0, 0, 0, 2, 0, 0, 0, 6],
    [0, 6, 0, 0, 0, 0, 2, 8, 0],
    [0, 0, 0, 4, 1, 9, 0, 0, 5],
    [0, 0, 0, 0, 8, 0, 0, 7, 9],
]


def test_a_puzzle_with_many_empty_cells_and_no_repeat_is_clean():
    assert violations(PUZZLE) == []
    assert conflict_cells(PUZZLE) == []
    assert is_solved(PUZZLE) is False


def test_the_same_puzzle_with_one_wrong_clue_is_reported():
    grid = copy.deepcopy(PUZZLE)
    grid[0][2] = 5  # a second 5 in row 0, and in box 0
    assert violations(grid) == [("row", 0, 5), ("box", 0, 5)]
    assert conflict_cells(grid) == [(0, 0), (0, 2)]


def test_a_clue_that_clashes_with_a_column_only():
    grid = copy.deepcopy(PUZZLE)
    grid[8][0] = 5  # column 0 already has the 5 at the top; box 6 and row 8 do not
    assert violations(grid) == [("col", 0, 5)]
    assert conflict_cells(grid) == [(0, 0), (8, 0)]


def test_the_grid_is_not_changed():
    grid = copy.deepcopy(PUZZLE)
    grid[0][2] = 5
    before = copy.deepcopy(grid)
    violations(grid)
    conflict_cells(grid)
    is_solved(grid)
    assert grid == before


def test_the_results_are_new_lists():
    a, b = violations(PUZZLE), violations(PUZZLE)
    assert a == b == []
    a.append(("row", 0, 1))
    assert violations(PUZZLE) == []


def test_tuples_of_tuples_work_like_lists():
    grid = tuple(tuple(row) for row in PUZZLE)
    assert violations(grid) == []
    bad = tuple(tuple(r) if i else (5, 3, 5, 0, 7, 0, 0, 0, 0) for i, r in enumerate(PUZZLE))
    assert violations(bad) == [("row", 0, 5), ("box", 0, 5)]
