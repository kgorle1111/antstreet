# Replacing the value of a live key keeps the old write time, so expiry does not restart.
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any


class LRUCache:
    def __init__(
        self,
        capacity: int,
        ttl: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if ttl is not None and ttl <= 0:
            raise ValueError("ttl must be positive")
        self._capacity = capacity
        self._ttl = ttl
        self._clock = clock
        # Ordered least to most recently used; each value is (value, time it was written).
        self._entries: OrderedDict[Hashable, tuple[Any, float]] = OrderedDict()

    def _now(self) -> float:
        """Read the clock and drop expired entries. Every operation starts here."""
        now = self._clock()
        if self._ttl is not None:
            expired = [k for k, (_, at) in self._entries.items() if now - at >= self._ttl]
            for key in expired:
                del self._entries[key]
        return now

    def get(self, key: Hashable, default: Any = None) -> Any:
        self._now()
        if key not in self._entries:
            return default
        self._entries.move_to_end(key)
        return self._entries[key][0]

    def put(self, key: Hashable, value: Any) -> None:
        now = self._now()
        if key not in self._entries and len(self._entries) >= self._capacity:
            self._entries.popitem(last=False)
        self._entries[key] = (value, self._entries[key][1] if key in self._entries else now)
        self._entries.move_to_end(key)

    def keys(self) -> list[Hashable]:
        self._now()
        return list(self._entries)

    def __len__(self) -> int:
        self._now()
        return len(self._entries)

    def __contains__(self, key: Hashable) -> bool:
        self._now()
        return key in self._entries
