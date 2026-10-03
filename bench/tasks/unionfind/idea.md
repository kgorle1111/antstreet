Create a Python module `unionfind.py` (standard library only) with one class:

    UnionFind(elements: Iterable = ())

    add(x) -> bool
    find(x) -> element
    union(a, b) -> bool
    connected(a, b) -> bool
    size(x) -> int
    groups() -> list[list]
    len(uf) -> int
    x in uf -> bool
    uf.num_sets -> int

It keeps a collection of disjoint sets of hashable elements and merges them on request.

1. `UnionFind(elements)` adds each element in order, ignoring repeats. Every element starts out in
   a set of its own. `len(uf)` is the number of elements, `x in uf` is `True` for a known
   element, and `uf.num_sets` is the current number of sets.
2. `add(x)` makes a new element `x` that is alone in its own set and returns `True`. When `x` is
   already known it returns `False` and changes nothing.
3. `find(x)` returns the representative of `x`'s set: one of the elements of that set, the same
   one for every member. An element alone in its set is its own representative. Calling `find`
   never changes a representative; only `union` does.
4. `union(a, b)` merges the set of `a` with the set of `b` and returns `True`, or returns `False`
   when they were already the same set (including `union(a, a)`), changing nothing. The merged
   set's representative is the representative of the larger of the two sets, larger meaning more
   elements. When both sets have the same number of elements it is the representative of `a`'s set.
5. `connected(a, b)` is `True` exactly when `a` and `b` are in the same set. `connected(a, a)` is
   `True`. `size(x)` is the number of elements in `x`'s set.
6. `find`, `connected`, `size` and `union` raise `KeyError` for an element that was never added.
   `union` checks both elements first: when either is unknown it raises and changes nothing, and
   in particular it does not add the other one.
7. `groups()` returns a new list holding one new list per set, with each set's elements in the order
   they were added. The sets are ordered by the position at which each set's earliest-added element
   was added. So after `UnionFind([3, 1, 2])` and `union(1, 3)`, `groups()` is `[[3, 1], [2]]`.
8. It must stay fast: 100,000 elements joined one after another into a single set, followed by a
   `find` on every element, must finish in a few seconds.
