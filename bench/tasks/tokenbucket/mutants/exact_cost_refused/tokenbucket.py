# Allow refuses when exactly cost tokens are available; exactly enough must be allowed.
import time
from collections.abc import Callable


class TokenBucket:
    def __init__(
        self,
        rate: float,
        capacity: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._rate = rate
        self._capacity = capacity
        self._clock = clock
        self._tokens = float(capacity)
        self._last = clock()  # latest reading seen; never moves backwards

    def _refill(self) -> None:
        now = self._clock()
        if now > self._last:
            gained = (now - self._last) * self._rate
            self._tokens = min(float(self._capacity), self._tokens + gained)
            self._last = now

    @staticmethod
    def _check_cost(cost: float) -> None:
        if cost <= 0:
            raise ValueError("cost must be positive")

    def allow(self, cost: float = 1) -> bool:
        self._check_cost(cost)
        self._refill()
        if cost >= self._tokens:
            return False
        self._tokens -= cost
        return True

    def available(self) -> float:
        self._refill()
        return self._tokens

    def wait_time(self, cost: float = 1) -> float:
        self._check_cost(cost)
        if cost > self._capacity:
            raise ValueError("cost exceeds capacity and can never be satisfied")
        self._refill()
        return max(0.0, (cost - self._tokens) / self._rate)
