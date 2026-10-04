import pytest
from sudokucheck import violations


def grid_with(cells):
    grid = [[0] * 9 for _ in range(9)]
    for (r, c), digit in cells.items():
        grid[r][c] = digit
    return grid


@pytest.mark.parametrize("col", range(9))
def test_a_repeat_in_each_column(col):
    grid = grid_with({(0, col): 8, (8, col): 8})
    assert violations(grid) == [("col", col, 8)]


@pytest.mark.parametrize("box", range(9))
def test_a_repeat_in_each_box_is_reported_under_the_reading_order_number(box):
    top, left = 3 * (box // 3), 3 * (box % 3)
    grid = grid_with({(top, left): 6, (top + 1, left + 1): 6})
    assert violations(grid) == [("box", box, 6)]
    grid = grid_with({(top + 2, left): 1, (top, left + 2): 1})
    assert violations(grid) == [("box", box, 1)]


def test_example_from_the_idea():
    assert violations(grid_with({(0, 0): 5, (1, 1): 5})) == [("box", 0, 5)]


def test_the_same_digit_in_different_boxes_is_fine():
    grid = grid_with({(0, 0): 5, (1, 4): 5, (2, 8): 5, (3, 1): 5, (4, 3): 5, (5, 6): 5})
    assert violations(grid) == []


def test_boxes_numbered_by_row_band_then_column_band():
    # the second box in the middle band is box 4, the first box of the bottom band is box 6
    assert violations(grid_with({(3, 3): 2, (5, 5): 2})) == [("box", 4, 2)]
    assert violations(grid_with({(6, 0): 2, (8, 2): 2})) == [("box", 6, 2)]
    assert violations(grid_with({(0, 6): 2, (2, 8): 2})) == [("box", 2, 2)]
    assert violations(grid_with({(3, 0): 2, (5, 2): 2})) == [("box", 3, 2)]


def test_a_digit_in_three_cells_of_a_column_or_box_is_one_violation():
    assert violations(grid_with({(0, 2): 9, (4, 2): 9, (7, 2): 9})) == [("col", 2, 9)]
    grid = grid_with({(0, 0): 9, (1, 1): 9, (2, 2): 9})
    assert violations(grid) == [("box", 0, 9)]


def test_the_same_pair_in_a_row_and_a_box_is_reported_for_both():
    assert violations(grid_with({(0, 0): 4, (0, 1): 4})) == [("row", 0, 4), ("box", 0, 4)]
    assert violations(grid_with({(0, 0): 4, (1, 0): 4})) == [("col", 0, 4), ("box", 0, 4)]


def test_a_row_and_a_column_through_one_cell():
    grid = grid_with({(0, 0): 9, (0, 5): 9, (5, 0): 9})
    assert violations(grid) == [("row", 0, 9), ("col", 0, 9)]
