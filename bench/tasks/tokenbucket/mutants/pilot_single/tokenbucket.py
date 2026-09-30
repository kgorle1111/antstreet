# Harvested: a Haiku worker's product (pilot run, single arm, rep1); fails hidden checks: basic.
import time
from typing import Callable


class TokenBucket:
    def __init__(self, rate: float, capacity: float, clock: Callable[[], float] = time.monotonic):
        if rate <= 0:
            raise ValueError("rate must be greater than 0")
        if capacity <= 0:
            raise ValueError("capacity must be greater than 0")

        self.rate = rate
        self.capacity = capacity
        self.clock = clock
        self.current_tokens = capacity
        self.last_clock_reading = clock()

    def _refill(self) -> None:
        now = self.clock()
        if now > self.last_clock_reading:
            elapsed = now - self.last_clock_reading
            self.current_tokens = min(self.current_tokens + elapsed * self.rate, self.capacity)
            self.last_clock_reading = now

    def available(self) -> float:
        self._refill()
        return self.current_tokens

    def allow(self, cost: float = 1) -> bool:
        if cost <= 0:
            raise ValueError("cost must be greater than 0")

        self._refill()

        if cost > self.capacity:
            return False

        if self.current_tokens >= cost:
            self.current_tokens -= cost
            return True

        return False

    def wait_time(self, cost: float = 1) -> float:
        if cost <= 0:
            raise ValueError("cost must be greater than 0")

        if cost > self.capacity:
            raise ValueError("cost cannot exceed capacity")

        self._refill()

        if self.current_tokens >= cost:
            return 0.0

        return (cost - self.current_tokens) / self.rate
