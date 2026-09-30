Create a Python module `linediff.py` (standard library only; do not import `difflib`) with three
functions:

    diff(old: list[str], new: list[str]) -> list[tuple[str, str]]
    apply(old: list[str], diff_ops: list[tuple[str, str]]) -> list[str]
    stats(diff_ops: list[tuple[str, str]]) -> dict[str, int]

A diff is a list of `(op, line)` tuples where `op` is `" "` (line kept), `"-"` (line removed from
`old`) or `"+"` (line added in `new`). Lines are compared with `==` exactly: no stripping, no case
folding, and the empty string is an ordinary line.

1. `diff` returns a list of tuples. The kept and removed lines, in order, equal `old`. The kept and
   added lines, in order, equal `new`.
2. The diff is minimal: the number of kept lines equals the length of the longest common
   subsequence of `old` and `new`.
3. Within every run of consecutive changes (the ops between two kept lines, or before the first or
   after the last kept line), all `"-"` ops come before all `"+"` ops. Replacing line `a` by `b`
   gives `[("-", "a"), ("+", "b")]`.
4. When several diffs satisfy rules 1 to 3, any one of them is acceptable. Two empty lists give
   `[]`; identical lists give only kept lines. `diff` does not modify its arguments.
5. `apply` returns a new list and does not modify `old`. It walks `diff_ops` in order with a
   position in `old`. A `" "` or `"-"` op consumes the next unconsumed line of `old`, which must
   equal the op's line. A `"+"` op appends its line to the result and consumes nothing. A `" "` op
   also appends its line to the result.
6. `apply` raises `ValueError` if a `" "` or `"-"` op does not match the next line of `old` (this
   includes the case where no lines of `old` are left), if any lines of `old` remain unconsumed
   after the last op, or if an op is not one of `" "`, `"-"`, `"+"`. `apply` does not require the
   ops to be in the order `diff` produces or to be minimal: any sequence meeting rules 5 and 6
   is applied. For every `old` and `new`, `apply(old, diff(old, new)) == new`.
7. `stats` returns a dict with exactly the keys `"kept"`, `"added"` and `"removed"`, holding the
   number of `" "`, `"+"` and `"-"` ops. An empty diff gives all zeros.
8. Inputs of up to 2,000 lines each must be handled without recursion errors and within a few
   seconds.
