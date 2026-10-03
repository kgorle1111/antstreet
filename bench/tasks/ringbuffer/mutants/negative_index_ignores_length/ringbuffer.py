# A negative index is taken relative to the oldest slot instead of the item count, so it is only right when the buffer is full.
import operator
from collections.abc import Iterable, Iterator
from typing import Any


class BufferFull(Exception):
    pass


class RingBuffer:
    def __init__(self, capacity: int, overwrite: bool = True) -> None:
        if not isinstance(capacity, int):
            raise TypeError(f"capacity must be an int, got {type(capacity).__name__}")
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self._slots: list[Any] = [None] * capacity
        self._overwrite = overwrite
        # `_head` is the slot of the oldest item; the newest is `_size - 1` slots after it.
        self._head = 0
        self._size = 0

    @property
    def capacity(self) -> int:
        return len(self._slots)

    @property
    def full(self) -> bool:
        return self._size == len(self._slots)

    def append(self, item: Any) -> None:
        cap = len(self._slots)
        if self._size == cap:
            if not self._overwrite:
                raise BufferFull("buffer is full")
            self._slots[self._head] = item
            self._head = (self._head + 1) % cap
        else:
            self._slots[(self._head + self._size) % cap] = item
            self._size += 1

    def extend(self, items: Iterable[Any]) -> None:
        for item in items:
            self.append(item)

    def popleft(self) -> Any:
        if not self._size:
            raise IndexError("popleft from an empty RingBuffer")
        item = self._slots[self._head]
        self._slots[self._head] = None
        self._head = (self._head + 1) % len(self._slots)
        self._size -= 1
        return item

    def clear(self) -> None:
        self._slots = [None] * len(self._slots)
        self._head = 0
        self._size = 0

    def __getitem__(self, index: int) -> Any:
        i = operator.index(index)
        if not -self._size <= i < self._size:
            raise IndexError("RingBuffer index out of range")
        if i < 0:
            i += len(self._slots)
        return self._slots[(self._head + i) % len(self._slots)]

    def __iter__(self) -> Iterator[Any]:
        for i in range(self._size):
            yield self._slots[(self._head + i) % len(self._slots)]

    def __len__(self) -> int:
        return self._size
