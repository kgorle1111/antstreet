# The script lists only the edits and leaves out the keep operations.
def _table(a: str, b: str) -> list[list[int]]:
    """d[i][j] is the edit distance between a[i:] and b[j:]."""
    n, m = len(a), len(b)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n, -1, -1):
        for j in range(m, -1, -1):
            if i == n:
                d[i][j] = m - j
            elif j == m:
                d[i][j] = n - i
            else:
                d[i][j] = min(
                    d[i + 1][j + 1] + (a[i] != b[j]),
                    d[i + 1][j] + 1,
                    d[i][j + 1] + 1,
                )
    return d


def _check(a: object, b: object) -> None:
    if not isinstance(a, str) or not isinstance(b, str):
        raise TypeError("both arguments must be str")


def edit_distance(a: str, b: str) -> int:
    _check(a, b)
    return _table(a, b)[0][0]


def edit_script(a: str, b: str) -> list[tuple[str, ...]]:
    _check(a, b)
    d = _table(a, b)
    i = j = 0
    script: list[tuple[str, ...]] = []
    while i < len(a) or j < len(b):
        here = d[i][j]
        if i < len(a) and j < len(b) and a[i] == b[j] and d[i + 1][j + 1] == here:
            pass
            i, j = i + 1, j + 1
        elif i < len(a) and j < len(b) and a[i] != b[j] and d[i + 1][j + 1] + 1 == here:
            script.append(("sub", a[i], b[j]))
            i, j = i + 1, j + 1
        elif i < len(a) and d[i + 1][j] + 1 == here:
            script.append(("delete", a[i]))
            i += 1
        else:
            script.append(("insert", b[j]))
            j += 1
    return script
