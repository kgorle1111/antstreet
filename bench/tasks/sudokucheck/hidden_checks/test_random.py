import random
from itertools import combinations

from sudokucheck import conflict_cells, is_solved, violations

CELLS = [(r, c) for r in range(9) for c in range(9)]


def units_of(cell):
    r, c = cell
    return {("row", r), ("col", c), ("box", 3 * (r // 3) + c // 3)}


def slow_answer(grid):
    """Every pair of cells that share a digit and a unit, found the long way round."""
    kinds = {"row": 0, "col": 1, "box": 2}
    found, cells = set(), set()
    for a, b in combinations(CELLS, 2):
        digit = grid[a[0]][a[1]]
        if digit == 0 or digit != grid[b[0]][b[1]]:
            continue
        for kind, index in units_of(a) & units_of(b):
            found.add((kind, index, digit))
            cells |= {a, b}
    return sorted(found, key=lambda v: (kinds[v[0]], v[1], v[2])), sorted(cells)


def random_grid(rng, fill):
    return [[rng.randint(1, 9) if rng.random() < fill else 0 for _ in range(9)] for _ in range(9)]


def test_random_grids_against_a_pairwise_search():
    rng = random.Random(99)
    for _ in range(150):
        grid = random_grid(rng, rng.choice([0.1, 0.25, 0.5, 1.0]))
        expected_violations, expected_cells = slow_answer(grid)
        assert violations(grid) == expected_violations
        assert conflict_cells(grid) == expected_cells
        assert is_solved(grid) is False


def test_sparse_grids_are_often_clean_and_then_nothing_is_reported():
    rng = random.Random(3)
    clean = 0
    for _ in range(300):
        grid = random_grid(rng, 0.08)
        expected_violations, expected_cells = slow_answer(grid)
        assert violations(grid) == expected_violations
        assert conflict_cells(grid) == expected_cells
        clean += not expected_violations
    assert clean > 0


def test_perturbed_solutions_against_a_pairwise_search():
    solved = [
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
    rng = random.Random(12)
    for _ in range(150):
        grid = [row[:] for row in solved]
        for _ in range(rng.randint(0, 4)):
            r, c = rng.choice(CELLS)
            grid[r][c] = rng.randint(0, 9)
        expected_violations, expected_cells = slow_answer(grid)
        assert violations(grid) == expected_violations
        assert conflict_cells(grid) == expected_cells
        assert is_solved(grid) is (not expected_violations and all(all(row) for row in grid))
