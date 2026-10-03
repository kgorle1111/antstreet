Create a Python module `circuitbreaker.py` (standard library only) with one class:

    CircuitBreaker(failure_threshold: int = 5, reset_timeout: float = 30.0, half_open_successes: int = 1)

    state(now: float) -> str
    allow(now: float) -> bool
    record_success(now: float) -> None
    record_failure(now: float) -> None

It is a circuit breaker for calls to an unreliable service. It never reads a clock: every method
takes the current time `now` (seconds, a number) from the caller, and tests pass times directly.
`now` never goes backwards between calls.

1. `failure_threshold` below 1, `reset_timeout` not greater than 0, or `half_open_successes`
   below 1 raises `ValueError` from the constructor.
2. `state(now)` returns one of the strings `"closed"`, `"open"` or `"half_open"`. A new breaker is
   `"closed"`. `state` never changes anything.
3. While closed, `allow` returns `True`. `record_failure` counts one failure, and
   `record_success` resets that count to 0, so only consecutive failures count. When the count
   reaches `failure_threshold` the breaker opens at that `now`.
4. While open, `allow` returns `False`. The breaker is open until `reset_timeout` seconds have passed
   since it opened: at `now - opened_at >= reset_timeout` (exactly `reset_timeout` is enough) its
   state is `"half_open"`; before that it is `"open"`.
5. `record_success` and `record_failure` called while the state at `now` is `"open"` are ignored:
   they change nothing, and in particular a failure does not restart the open period.
6. While half open, the breaker lets one trial call through at a time. `allow` returns `True` the
   first time and then `False` until that trial is reported with `record_success` or
   `record_failure`. A trial that is never reported blocks further trials; there is no timeout
   for it.
7. In the half-open state `record_success` counts one successful trial, and the next trial is
   allowed again. When the count reaches `half_open_successes` the breaker closes with its
   failure count at 0. `record_failure` in the half-open state opens the breaker again at that
   `now`, so the open period restarts from it, and throws away the successful trials counted so far.
8. After the breaker has been re-opened, or has closed again, it starts from a clean slate: a
   closed breaker needs `failure_threshold` new consecutive failures to open, and a half-open one
   needs `half_open_successes` new successful trials to close.
