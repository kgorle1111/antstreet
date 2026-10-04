Create a Python module `sudokucheck.py` (standard library only) that checks a 9 by 9 sudoku grid
and says where it breaks the rules, with three functions:

    violations(grid: list[list[int]]) -> list[tuple[str, int, int]]
    conflict_cells(grid: list[list[int]]) -> list[tuple[int, int]]
    is_solved(grid: list[list[int]]) -> bool

1. `grid` is a list (or tuple) of 9 rows, each a list (or tuple) of 9 ints. `0` is an empty cell and
   `1` to `9` are digits. Row 0 is the top row and column 0 is the left column. The 3 by 3 boxes are
   numbered 0 to 8 in reading order: box 0 is the top-left, box 1 the top-middle, box 2 the
   top-right, box 3 the middle-left, and so on to box 8 at the bottom-right. The cell in row `r`
   and column `c` is in box `3 * (r // 3) + c // 3`.
2. A unit is a row, a column or a box. A unit is broken for a digit when that digit (1 to 9) is in
   two or more of its cells. Empty cells never count, however many a unit has, so an unfinished
   grid with no repeated digit has no violations.
3. `violations(grid)` returns one tuple `(kind, index, digit)` for each broken unit and digit:
   `kind` is `"row"`, `"col"` or `"box"`, `index` is the row number, column number or box number,
   and `digit` is the repeated digit. A digit that is in three cells of a unit is still one tuple.
   The list is sorted by kind in the order `"row"`, `"col"`, `"box"`, then by `index`, then by
   `digit`, each ascending. A grid with no violation gives `[]`. For example a grid with a 5 at
   row 0 column 0 and a 5 at row 0 column 8 and nothing else gives `[("row", 0, 5)]`, and with the
   5s at row 0 column 0 and row 1 column 1 it gives `[("box", 0, 5)]`.
4. `conflict_cells(grid)` returns the cells that are part of a violation: every non-empty cell whose
   digit is also found in another cell of its row, its column or its box, as `(row, column)` tuples
   sorted by row and then by column, each cell once. A grid with no violation gives `[]`.
5. `is_solved(grid)` is `True` only when there are no empty cells and no violations, and `False`
   otherwise (a full grid with a repeated digit is not solved, and neither is a valid unfinished
   grid).
6. A `grid` or a row that is not a list or tuple raises `TypeError`, and so does a cell that is not
   an `int` (a `bool` is not one). A grid without exactly 9 rows, a row without exactly 9 cells, or
   an int cell below 0 or above 9 raises `ValueError`. All three functions check the whole grid
   first, including cells that would not matter.
