# connected compares the elements' direct parents without finding the roots, so deeper members look unconnected.
from collections.abc import Hashable, Iterable
from typing import Any


class UnionFind:
    def __init__(self, elements: Iterable[Hashable] = ()) -> None:
        # Insertion order of `_parent` is the order elements were added; `groups` relies on it.
        self._parent: dict[Any, Any] = {}
        self._size: dict[Any, int] = {}  # set size, kept for roots only
        for element in elements:
            self.add(element)

    @property
    def num_sets(self) -> int:
        return len(self._size)

    def add(self, x: Hashable) -> bool:
        if x in self._parent:
            return False
        self._parent[x] = x
        self._size[x] = 1
        return True

    def find(self, x: Hashable) -> Any:
        if x not in self._parent:
            raise KeyError(x)
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: Hashable, b: Hashable) -> bool:
        root_a, root_b = self.find(a), self.find(b)
        if root_a == root_b:
            return False
        if self._size[root_b] > self._size[root_a]:
            root_a, root_b = root_b, root_a
        self._parent[root_b] = root_a
        self._size[root_a] += self._size.pop(root_b)
        return True

    def connected(self, a: Hashable, b: Hashable) -> bool:
        return self._parent[a] == self._parent[b]

    def size(self, x: Hashable) -> int:
        return self._size[self.find(x)]

    def groups(self) -> list[list[Any]]:
        by_root: dict[Any, list[Any]] = {}
        for element in self._parent:
            by_root.setdefault(self.find(element), []).append(element)
        return list(by_root.values())

    def __len__(self) -> int:
        return len(self._parent)

    def __contains__(self, x: object) -> bool:
        return x in self._parent
