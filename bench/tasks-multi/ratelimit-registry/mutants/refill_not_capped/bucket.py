# Refill is not capped at capacity, so an idle bucket stores unlimited tokens.
import math
import time


class TokenBucket:
    def __init__(self, capacity, refill_rate, clock=time.monotonic):
        if not capacity > 0:
            raise ValueError("capacity must be greater than 0")
        if not refill_rate > 0:
            raise ValueError("refill_rate must be greater than 0")
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._clock = clock
        self._tokens = float(capacity)
        self._last = clock()

    def _refill(self):
        now = self._clock()
        elapsed = max(0.0, now - self._last)
        self._last = now
        self._tokens = self._tokens + elapsed * self.refill_rate

    def try_acquire(self, n=1):
        if not n > 0:
            raise ValueError("n must be greater than 0")
        self._refill()
        if n > self._tokens:
            return False
        self._tokens -= n
        return True

    def available(self):
        self._refill()
        return self._tokens

    def retry_after(self, n=1):
        if not n > 0:
            raise ValueError("n must be greater than 0")
        self._refill()
        if n > self.capacity:
            return math.inf
        if n <= self._tokens:
            return 0.0
        return (n - self._tokens) / self.refill_rate
