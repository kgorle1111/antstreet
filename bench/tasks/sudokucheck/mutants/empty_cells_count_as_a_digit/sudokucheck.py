# Empty cells are counted like a digit, so any unit with two empty cells is reported as broken.
from collections import Counter

_KINDS = ("row", "col", "box")


def _check(grid: object) -> None:
    if not isinstance(grid, list | tuple):
        raise TypeError("the grid must be a list of 9 rows")
    if len(grid) != 9:
        raise ValueError(f"the grid must have 9 rows, got {len(grid)}")
    for row in grid:
        if not isinstance(row, list | tuple):
            raise TypeError("every row must be a list of 9 numbers")
        if len(row) != 9:
            raise ValueError(f"every row must have 9 cells, got {len(row)}")
        for value in row:
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"a cell must be an int, got {value!r}")
            if not 0 <= value <= 9:
                raise ValueError(f"a cell must be 0 to 9, got {value}")


def _cells(kind: str, index: int) -> list[tuple[int, int]]:
    if kind == "row":
        return [(index, c) for c in range(9)]
    if kind == "col":
        return [(r, index) for r in range(9)]
    top, left = 3 * (index // 3), 3 * (index % 3)
    return [(top + r, left + c) for r in range(3) for c in range(3)]


def violations(grid: list[list[int]]) -> list[tuple[str, int, int]]:
    _check(grid)
    found = []
    for kind in _KINDS:
        for index in range(9):
            counts = Counter(grid[r][c] for r, c in _cells(kind, index))
            found += [(kind, index, d) for d in range(0, 10) if counts[d] > 1]
    return found


def conflict_cells(grid: list[list[int]]) -> list[tuple[int, int]]:
    _check(grid)
    bad = set()
    for kind in _KINDS:
        for index in range(9):
            cells = _cells(kind, index)
            counts = Counter(grid[r][c] for r, c in cells)
            bad |= {(r, c) for r, c in cells if grid[r][c] and counts[grid[r][c]] > 1}
    return sorted(bad)


def is_solved(grid: list[list[int]]) -> bool:
    _check(grid)
    return all(all(row) for row in grid) and not violations(grid)
