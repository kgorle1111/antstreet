# Harvested: a Haiku worker's product (rerun1 run, firm arm, rep1); fails hidden checks: basic.
import time
from typing import Callable


class TokenBucket:
    def __init__(self, rate: float, capacity: float, clock: Callable[[], float] = time.monotonic):
        if rate <= 0:
            raise ValueError("rate must be positive")
        if capacity <= 0:
            raise ValueError("capacity must be positive")

        self.rate = rate
        self.capacity = capacity
        self.clock = clock

        self.last_refill_time = clock()
        self.tokens = capacity

    def available(self) -> float:
        now = self.clock()
        if now > self.last_refill_time:
            dt = now - self.last_refill_time
            refill = dt * self.rate
            self.tokens = min(self.tokens + refill, self.capacity)
            self.last_refill_time = now

        return self.tokens

    def allow(self, cost: float = 1) -> bool:
        if cost <= 0:
            raise ValueError("cost must be positive")

        if cost > self.capacity:
            return False

        if self.available() >= cost:
            self.tokens -= cost
            return True
        else:
            return False

    def wait_time(self, cost: float = 1) -> float:
        if cost <= 0:
            raise ValueError("cost must be positive")

        if cost > self.capacity:
            raise ValueError("cost exceeds capacity")

        available = self.available()
        if available >= cost:
            return 0.0

        needed = cost - available
        wait = needed / self.rate
        return wait
