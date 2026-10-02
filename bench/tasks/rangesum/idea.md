Create a Python module `rangesum.py` (standard library only) with one class:

    RangeSum(values: Iterable[int] = ())

    get(i) -> int
    set(i, value) -> None
    update(i, delta) -> None
    prefix(n) -> int
    range_sum(lo, hi) -> int
    len(rs) -> int

It holds a fixed-length sequence of integers and answers sums over ranges of it while single
elements change. Positions are 0-based.

1. `RangeSum(values)` takes its own copy of the values: changing the list that was passed in
   afterwards does not affect it, and it never changes that list. `len(rs)` is the number of values
   and never changes. An empty sequence is allowed.
2. `get(i)` returns the current value at position `i`. `set(i, value)` replaces it. `update(i,
   delta)` adds `delta` to it; `delta` may be negative or zero.
3. `prefix(n)` is the sum of the first `n` elements, positions `0` to `n - 1`. `prefix(0)` is `0`
   and `prefix(len(rs))` is the sum of everything.
4. `range_sum(lo, hi)` is the sum of the elements at positions `lo <= i < hi`: `lo` is included and
   `hi` is not. When `lo == hi` it is `0`, for any `lo` from `0` to `len(rs)`.
5. Errors, checked in this order. An index argument that is not an `int` (a float such as `1.0`,
   a string, `None`) raises `TypeError`. For `range_sum`, `lo > hi` raises `ValueError`. Then a
   position that is out of range raises `IndexError`: for `get`, `set` and `update`, `i` outside `0`
   to `len(rs) - 1`; for `prefix`, `n` outside `0` to `len(rs)`; for `range_sum`, `lo < 0` or
   `hi > len(rs)`. Negative positions are errors, they do not count from the end. An operation that
   raises leaves the contents unchanged.
6. It must stay fast: 100,000 values with 50,000 mixed updates and range queries must finish in a
   few seconds.
