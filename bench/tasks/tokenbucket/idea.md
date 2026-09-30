Create a Python module `tokenbucket.py` (standard library only) with one class:

    TokenBucket(rate: float, capacity: float, clock: Callable[[], float] = time.monotonic)

    allow(cost: float = 1) -> bool
    available() -> float
    wait_time(cost: float = 1) -> float

It is a token-bucket rate limiter. `rate`, `capacity` and `cost` are positive numbers (int or
float); costs may be fractional.

1. `rate`, `capacity` and `cost` must be greater than 0, otherwise `ValueError` is raised: from
   the constructor for `rate` and `capacity`, and from `allow` and `wait_time` for `cost`.
2. `clock` is a function taking no arguments that returns the current time in seconds. The
   bucket is created at the clock's current reading, and every call to `allow`, `available` or
   `wait_time` reads the clock once to learn the current time. Tests pass a fake clock and never
   sleep.
3. A new bucket is full: it holds `capacity` tokens.
4. Tokens refill continuously, not in whole ticks: after `dt` seconds the bucket has gained
   `dt * rate` tokens, fractions included, but never holds more than `capacity`.
5. `available()` returns the current number of tokens as a `float`, refill included, at most
   `capacity`. It does not change the bucket.
6. `allow(cost=1)` returns `True` and removes `cost` tokens if at least `cost` tokens are
   available (exactly `cost` is enough). Otherwise it returns `False` and removes nothing, and
   the tokens refilled so far are kept: a refusal never loses refill progress. A `cost` greater
   than `capacity` can never be satisfied, so `allow` simply returns `False` for it.
7. `wait_time(cost=1)` returns, as a `float`, the number of seconds from now until `cost` tokens
   will be available if nothing else is taken meanwhile: `0.0` if they already are. It does not
   remove tokens. A `cost` greater than `capacity` raises `ValueError`, because the wait would
   never end.
8. The clock may go backwards. The bucket only counts time forward from the latest clock reading
   it has seen: a reading earlier than that adds no tokens, removes no tokens, and does not
   move that reference point. Refilling resumes once the clock passes the latest reading seen
   before.
