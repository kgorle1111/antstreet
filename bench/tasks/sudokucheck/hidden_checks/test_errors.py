import pytest
from sudokucheck import conflict_cells, is_solved, violations

ALL = [violations, conflict_cells, is_solved]


def empty():
    return [[0] * 9 for _ in range(9)]


@pytest.mark.parametrize("fn", ALL)
@pytest.mark.parametrize("bad", [None, "000000000", 5, {0: [0] * 9}, {1, 2}, 1.5])
def test_a_grid_that_is_not_a_list_raises_type_error(fn, bad):
    with pytest.raises(TypeError):
        fn(bad)


@pytest.mark.parametrize("fn", ALL)
@pytest.mark.parametrize("count", [0, 1, 8, 10])
def test_a_grid_without_nine_rows_raises_value_error(fn, count):
    with pytest.raises(ValueError):
        fn([[0] * 9 for _ in range(count)])


@pytest.mark.parametrize("fn", ALL)
@pytest.mark.parametrize("bad", ["000000000", None, 7, {0: 1}, {0, 1}])
def test_a_row_that_is_not_a_list_raises_type_error(fn, bad):
    grid = empty()
    grid[8] = bad
    with pytest.raises(TypeError):
        fn(grid)


@pytest.mark.parametrize("fn", ALL)
@pytest.mark.parametrize("length", [0, 1, 8, 10])
def test_a_row_without_nine_cells_raises_value_error(fn, length):
    for position in (0, 4, 8):
        grid = empty()
        grid[position] = [0] * length
        with pytest.raises(ValueError):
            fn(grid)


@pytest.mark.parametrize("fn", ALL)
@pytest.mark.parametrize("bad", [1.0, "1", None, True, False, [1], 5.5, 1 + 0j])
def test_a_cell_that_is_not_an_int_raises_type_error(fn, bad):
    for r, c in ((0, 0), (4, 4), (8, 8)):
        grid = empty()
        grid[r][c] = bad
        with pytest.raises(TypeError):
            fn(grid)


@pytest.mark.parametrize("fn", ALL)
@pytest.mark.parametrize("bad", [10, -1, 99, 100, -9])
def test_a_cell_outside_zero_to_nine_raises_value_error(fn, bad):
    for r, c in ((0, 0), (4, 4), (8, 8)):
        grid = empty()
        grid[r][c] = bad
        with pytest.raises(ValueError):
            fn(grid)


@pytest.mark.parametrize("fn", ALL)
def test_the_whole_grid_is_checked_even_when_a_violation_is_found_earlier(fn):
    grid = empty()
    grid[0][0] = grid[0][1] = 5
    grid[8][8] = 10
    with pytest.raises(ValueError):
        fn(grid)
    grid[8][8] = "x"
    with pytest.raises(TypeError):
        fn(grid)
