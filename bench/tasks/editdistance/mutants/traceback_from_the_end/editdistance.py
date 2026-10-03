# The script is traced back from the ends of the strings, so ties resolve from the right.
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
    n, m = len(a), len(b)
    p = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        for j in range(m + 1):
            if i == 0 or j == 0:
                p[i][j] = i + j
            else:
                p[i][j] = min(
                    p[i - 1][j - 1] + (a[i - 1] != b[j - 1]), p[i - 1][j] + 1, p[i][j - 1] + 1
                )
    i, j = n, m
    script: list[tuple[str, ...]] = []
    while i > 0 or j > 0:
        if i and j and a[i - 1] == b[j - 1] and p[i][j] == p[i - 1][j - 1]:
            script.append(("keep", a[i - 1]))
            i, j = i - 1, j - 1
        elif i and j and a[i - 1] != b[j - 1] and p[i][j] == p[i - 1][j - 1] + 1:
            script.append(("sub", a[i - 1], b[j - 1]))
            i, j = i - 1, j - 1
        elif i and p[i][j] == p[i - 1][j] + 1:
            script.append(("delete", a[i - 1]))
            i -= 1
        else:
            script.append(("insert", b[j - 1]))
            j -= 1
    return script[::-1]
