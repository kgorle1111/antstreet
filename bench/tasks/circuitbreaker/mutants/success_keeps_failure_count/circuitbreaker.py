# A success does not reset the failure count, so non-consecutive failures add up.
class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 30.0,
        half_open_successes: int = 1,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if reset_timeout <= 0:
            raise ValueError("reset_timeout must be positive")
        if half_open_successes < 1:
            raise ValueError("half_open_successes must be at least 1")
        self._threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._needed = half_open_successes
        self._tripped = False  # open or half open; which one depends on `now`
        self._opened_at = 0.0
        self._failures = 0
        self._successes = 0
        self._trial_out = False

    def state(self, now: float) -> str:
        if not self._tripped:
            return "closed"
        if now - self._opened_at >= self._reset_timeout:
            return "half_open"
        return "open"

    def _trip(self, now: float) -> None:
        self._tripped = True
        self._opened_at = now
        self._failures = 0
        self._successes = 0
        self._trial_out = False

    def allow(self, now: float) -> bool:
        state = self.state(now)
        if state == "closed":
            return True
        if state == "open" or self._trial_out:
            return False
        self._trial_out = True
        return True

    def record_success(self, now: float) -> None:
        state = self.state(now)
        if state == "closed":
            pass
        elif state == "half_open":
            self._trial_out = False
            self._successes += 1
            if self._successes >= self._needed:
                self._tripped = False
                self._failures = 0
                self._successes = 0

    def record_failure(self, now: float) -> None:
        state = self.state(now)
        if state == "closed":
            self._failures += 1
            if self._failures >= self._threshold:
                self._trip(now)
        elif state == "half_open":
            self._trip(now)
