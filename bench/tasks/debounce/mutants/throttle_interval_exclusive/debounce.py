# A call exactly one interval after the last run is still throttled; it needs to be later.
from typing import Any


class Debouncer:
    def __init__(self, wait: float, max_wait: float | None = None) -> None:
        if wait <= 0:
            raise ValueError("wait must be positive")
        if max_wait is not None and max_wait < wait:
            raise ValueError("max_wait must be at least wait")
        self._wait = wait
        self._max_wait = max_wait
        self._pending = False
        self._first = 0.0  # start of the burst
        self._last = 0.0  # latest call
        self._value: Any = None

    def call(self, now: float, value: Any = None) -> None:
        if not self._pending:
            self._pending = True
            self._first = now
        self._last = now
        self._value = value

    def pending(self) -> bool:
        return self._pending

    def cancel(self) -> None:
        self._pending = False
        self._value = None

    def poll(self, now: float) -> list[Any]:
        if not self._pending:
            return []
        quiet = now - self._last >= self._wait
        forced = self._max_wait is not None and now - self._first >= self._max_wait
        if not (quiet or forced):
            return []
        value, self._value = self._value, None
        self._pending = False
        return [value]


class Throttler:
    def __init__(self, interval: float, trailing: bool = True) -> None:
        if interval <= 0:
            raise ValueError("interval must be positive")
        self._interval = interval
        self._trailing = trailing
        self._last_run: float | None = None
        self._pending = False
        self._value: Any = None

    def call(self, now: float, value: Any = None) -> list[Any]:
        if self._last_run is None or now - self._last_run > self._interval:
            self._last_run = now
            self._pending = False
            self._value = None
            return [value]
        if self._trailing:
            self._pending = True
            self._value = value
        return []

    def pending(self) -> bool:
        return self._pending

    def poll(self, now: float) -> list[Any]:
        if not self._pending or self._last_run is None or now - self._last_run < self._interval:
            return []
        value, self._value = self._value, None
        self._pending = False
        self._last_run = now
        return [value]
