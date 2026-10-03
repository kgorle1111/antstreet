import pytest
from sudokucheck import violations


def grid_with(cells):
    grid = [[0] * 9 for _ in range(9)]
    for (r, c), digit in cells.items():
        grid[r][c] = digit
    return grid


@pytest.mark.parametrize("row", range(9))
def test_a_repeat_in_each_row(row):
    grid = grid_with({(row, 0): 3, (row, 8): 3})
    assert violations(grid) == [("row", row, 3)]


def test_example_from_the_idea():
    assert violations(grid_with({(0, 0): 5, (0, 8): 5})) == [("row", 0, 5)]


@pytest.mark.parametrize("digit", range(1, 10))
def test_every_digit_can_be_the_repeated_one(digit):
    assert violations(grid_with({(4, 1): digit, (4, 7): digit})) == [("row", 4, digit)]


def test_a_digit_in_three_cells_of_a_row_is_one_violation():
    grid = grid_with({(5, 0): 4, (5, 3): 4, (5, 6): 4})
    assert violations(grid) == [("row", 5, 4)]


def test_two_repeated_digits_in_one_row_are_two_violations_in_digit_order():
    grid = grid_with({(3, 0): 7, (3, 4): 7, (3, 2): 2, (3, 8): 2})
    assert violations(grid) == [("row", 3, 2), ("row", 3, 7)]


def test_different_digits_in_a_row_are_fine():
    assert violations(grid_with({(0, c): c + 1 for c in range(9)})) == []


def test_empty_cells_are_not_a_repeated_digit():
    assert violations([[0] * 9 for _ in range(9)]) == []
    assert violations(grid_with({(2, 2): 1})) == []
    grid = grid_with({(0, 0): 1, (0, 1): 2, (0, 2): 3})
    assert violations(grid) == []
