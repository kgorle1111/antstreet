# replace pushes the new item before popping (heappushpop), so a smaller new item is returned.
import heapq
import itertools
from collections.abc import Callable
from typing import Any


class _Entry:
    """Orders by priority with `<` only, then by insertion number, so items are never compared."""

    __slots__ = ("item", "priority", "seq")

    def __init__(self, priority: Any, seq: int, item: Any) -> None:
        self.priority = priority
        self.seq = seq
        self.item = item

    def __lt__(self, other: "_Entry") -> bool:
        if self.priority < other.priority:
            return True
        if other.priority < self.priority:
            return False
        return self.seq < other.seq


class MinHeap:
    def __init__(self, key: Callable[[Any], Any] | None = None) -> None:
        self._key = key
        self._heap: list[_Entry] = []
        self._seq = itertools.count()

    def push(self, item: Any) -> None:
        priority = item if self._key is None else self._key(item)
        heapq.heappush(self._heap, _Entry(priority, next(self._seq), item))

    def pop(self) -> Any:
        if not self._heap:
            raise IndexError("pop from an empty MinHeap")
        return heapq.heappop(self._heap).item

    def peek(self) -> Any:
        if not self._heap:
            raise IndexError("peek at an empty MinHeap")
        return self._heap[0].item

    def replace(self, item: Any) -> Any:
        if not self._heap:
            raise IndexError("replace on an empty MinHeap")
        priority = item if self._key is None else self._key(item)
        entry = _Entry(priority, next(self._seq), item)
        return heapq.heappushpop(self._heap, entry).item

    def items(self) -> list[Any]:
        return [entry.item for entry in sorted(self._heap)]

    def __len__(self) -> int:
        return len(self._heap)
