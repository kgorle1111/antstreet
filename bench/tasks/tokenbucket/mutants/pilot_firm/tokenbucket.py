# Harvested: a Haiku worker's product (pilot run, firm arm, rep1); fails hidden checks: basic.
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
        self.tokens = capacity
        self.last_time = clock()

    def available(self) -> float:
        current_time = self.clock()

        if current_time > self.last_time:
            elapsed = current_time - self.last_time
            self.tokens += elapsed * self.rate
            self.tokens = min(self.tokens, self.capacity)
            self.last_time = current_time

        return self.tokens

    def allow(self, cost: float = 1) -> bool:
        if cost <= 0:
            raise ValueError("cost must be positive")

        if cost > self.capacity:
            return False

        available = self.available()

        if cost <= available:
            self.tokens -= cost
            return True

        return False

    def wait_time(self, cost: float = 1) -> float:
        if cost <= 0:
            raise ValueError("cost must be positive")

        if cost > self.capacity:
            raise ValueError("cost cannot exceed capacity")

        available = self.available()

        if cost <= available:
            return 0.0

        needed = cost - available
        return needed / self.rate
