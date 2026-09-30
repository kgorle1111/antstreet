# Apply does not check that a kept or removed line equals the next line of old.
def _core(a: list[str], b: list[str]) -> list[tuple[str, str]]:
    n, m = len(a), len(b)
    lcs = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if a[i] == b[j]:
                lcs[i][j] = lcs[i + 1][j + 1] + 1
            else:
                lcs[i][j] = max(lcs[i + 1][j], lcs[i][j + 1])
    ops: list[tuple[str, str]] = []
    removed: list[str] = []
    added: list[str] = []

    def flush() -> None:
        ops.extend(("-", line) for line in removed)
        ops.extend(("+", line) for line in added)
        removed.clear()
        added.clear()

    i = j = 0
    while i < n or j < m:
        if i < n and j < m and a[i] == b[j]:
            flush()
            ops.append((" ", a[i]))
            i += 1
            j += 1
        elif j == m or (i < n and lcs[i + 1][j] >= lcs[i][j + 1]):
            removed.append(a[i])
            i += 1
        else:
            added.append(b[j])
            j += 1
    flush()
    return ops


def diff(old: list[str], new: list[str]) -> list[tuple[str, str]]:
    shortest = min(len(old), len(new))
    head = 0
    while head < shortest and old[head] == new[head]:
        head += 1
    tail = 0
    while tail < shortest - head and old[-1 - tail] == new[-1 - tail]:
        tail += 1
    middle = _core(old[head : len(old) - tail], new[head : len(new) - tail])
    return (
        [(" ", line) for line in old[:head]]
        + middle
        + [(" ", line) for line in old[len(old) - tail :]]
    )


def apply(old: list[str], diff_ops: list[tuple[str, str]]) -> list[str]:
    result: list[str] = []
    pos = 0
    for op, line in diff_ops:
        if op == "+":
            result.append(line)
        elif op in (" ", "-"):
            if pos >= len(old):
                raise ValueError(f"diff does not fit old at line {pos}: {op!r} {line!r}")
            pos += 1
            if op == " ":
                result.append(line)
        else:
            raise ValueError(f"unknown op {op!r}")
    if pos != len(old):
        raise ValueError(f"{len(old) - pos} lines of old left over")
    return result


def stats(diff_ops: list[tuple[str, str]]) -> dict[str, int]:
    ops = [op for op, _ in diff_ops]
    return {"kept": ops.count(" "), "added": ops.count("+"), "removed": ops.count("-")}
