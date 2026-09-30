# Rotate turns counter-clockwise instead of clockwise.
def _validate(matrix: list[list]) -> int:
    """Return the column count; raise ValueError for ragged rows."""
    widths = {len(row) for row in matrix}
    if len(widths) > 1:
        raise ValueError("all rows must have the same length")
    return widths.pop() if widths else 0


def spiral(matrix: list[list]) -> list:
    cols = _validate(matrix)
    top, bottom, left, right = 0, len(matrix) - 1, 0, cols - 1
    out = []
    while top <= bottom and left <= right:
        out.extend(matrix[top][left : right + 1])
        out.extend(matrix[r][right] for r in range(top + 1, bottom + 1))
        if top < bottom:
            out.extend(matrix[bottom][c] for c in range(right - 1, left - 1, -1))
        if left < right:
            out.extend(matrix[r][left] for r in range(bottom - 1, top, -1))
        top, bottom, left, right = top + 1, bottom - 1, left + 1, right - 1
    return out


def transpose(matrix: list[list]) -> list[list]:
    _validate(matrix)
    return [list(col) for col in zip(*matrix, strict=True)]


def rotate(matrix: list[list], turns: int = 1) -> list[list]:
    if _validate(matrix) == 0:
        return []
    result = [list(row) for row in matrix]
    for _ in range(turns % 4):
        result = [list(row) for row in zip(*result, strict=True)][::-1]
    return result
