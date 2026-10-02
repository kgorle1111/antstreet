# update stops its climb one node early (`<` instead of `<=`), so sums that use the top node go stale.
from collections.abc import Iterable


def _require_int(*args: object) -> None:
    for arg in args:
        if not isinstance(arg, int):
            raise TypeError(f"expected an int, got {type(arg).__name__}")


class RangeSum:
    def __init__(self, values: Iterable[int] = ()) -> None:
        self._values = list(values)
        n = len(self._values)
        # Fenwick tree, 1-based: node j holds the sum of the (j & -j) elements ending at position j.
        self._tree = [0] * (n + 1)
        for j, value in enumerate(self._values, start=1):
            self._tree[j] += value
            parent = j + (j & -j)
            if parent <= n:
                self._tree[parent] += self._tree[j]

    def _check_position(self, i: int) -> None:
        _require_int(i)
        if not 0 <= i < len(self._values):
            raise IndexError(f"position {i} is outside 0..{len(self._values) - 1}")

    def _prefix(self, n: int) -> int:
        total = 0
        while n > 0:
            total += self._tree[n]
            n -= n & -n
        return total

    def get(self, i: int) -> int:
        self._check_position(i)
        return self._values[i]

    def set(self, i: int, value: int) -> None:
        self._check_position(i)
        self.update(i, value - self._values[i])

    def update(self, i: int, delta: int) -> None:
        self._check_position(i)
        self._values[i] += delta
        j = i + 1
        while j < len(self._values):
            self._tree[j] += delta
            j += j & -j

    def prefix(self, n: int) -> int:
        _require_int(n)
        if not 0 <= n <= len(self._values):
            raise IndexError(f"prefix length {n} is outside 0..{len(self._values)}")
        return self._prefix(n)

    def range_sum(self, lo: int, hi: int) -> int:
        _require_int(lo, hi)
        if lo > hi:
            raise ValueError(f"lo {lo} is greater than hi {hi}")
        if lo < 0 or hi > len(self._values):
            raise IndexError(f"range {lo}..{hi} is outside 0..{len(self._values)}")
        return self._prefix(hi) - self._prefix(lo)

    def __len__(self) -> int:
        return len(self._values)
