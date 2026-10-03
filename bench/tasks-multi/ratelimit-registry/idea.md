Create two Python modules, `bucket.py` and `registry.py` (standard library only): a single token bucket, and a rate limiter that keeps one bucket per key. Time always comes from an injected clock, so tests never sleep.

`bucket.py` provides one class:

    TokenBucket(capacity: float, refill_rate: float, clock: Callable[[], float] = time.monotonic)
    try_acquire(n: float = 1) -> bool
    available() -> float
    retry_after(n: float = 1) -> float

`registry.py` provides one class:

    RateLimiter(capacity: float, refill_rate: float, clock: Callable[[], float] = time.monotonic, max_keys: int | None = None)
    allow(key, cost: float = 1) -> bool
    remaining(key) -> float
    retry_after(key, cost: float = 1) -> float
    reset(key) -> bool
    keys() -> list
    len(limiter) -> int
    key in limiter -> bool

`clock` is a function taking no arguments that returns the current time in seconds as a number.

The bucket:

1. `capacity` and `refill_rate` must be greater than 0, otherwise `ValueError`. A bucket starts full: `available()` is `capacity` at once.
2. The bucket holds a number of tokens, never above `capacity` and never below 0. Tokens come back at `refill_rate` per second of clock time. Every method (`try_acquire`, `available`, `retry_after`) first reads the clock once and adds `(now - last) * refill_rate` tokens, capped at `capacity`, where `last` is the clock reading of the previous refill (the reading taken when the bucket was built, for the first one). Refill is continuous, so fractions of a token accumulate (with `refill_rate=0.5`, two seconds give one token).
3. If the clock goes backwards (`now` below `last`), no tokens are added or taken away, and `last` still becomes `now`: time is then measured from the earlier reading.
4. `try_acquire(n)` raises `ValueError` unless `n > 0`. If at least `n` tokens are available it removes them and returns `True`. Otherwise it returns `False` and removes nothing. Asking for more than `capacity` always returns `False`.
5. `available()` returns the current number of tokens as a `float`, without removing any.
6. `retry_after(n)` raises `ValueError` unless `n > 0`. It returns the number of seconds until `n` tokens will be available if nothing else is acquired: `0.0` when they are available now, `(n - tokens) / refill_rate` otherwise, and `math.inf` when `n` is more than `capacity`. It removes nothing.

The limiter:

7. `RateLimiter(capacity, refill_rate, clock, max_keys)` raises `ValueError` for a `capacity` or `refill_rate` the bucket would refuse, and for a `max_keys` that is not `None` and not an `int` of at least 1 (a `bool` is not accepted). Every bucket it creates has the same `capacity` and `refill_rate` and reads the same `clock`.
8. Keys are any hashable objects except `None`; `None` as a key raises `ValueError` from `allow`, `remaining`, `retry_after` and `reset`; `None in limiter` is just `False`.
9. A key has no bucket until `allow` is first called for it. `allow(key, cost)` raises `ValueError` unless `cost > 0` (this is checked before anything else happens, so a bad `cost` creates nothing). Then it creates the key's full bucket if there is none, makes the key the most recently used, and returns that bucket's `try_acquire(cost)`. A denied `allow` still counts as a use.
10. With `max_keys` set, creating a bucket for a new key when the limiter already tracks `max_keys` keys first forgets the least recently used key. A forgotten key that comes back starts again with a full bucket. Only `allow` makes a key more recently used. With `max_keys=None` there is no limit.
11. `remaining(key)` returns the key's `available()`, and `capacity` as a `float` for a key with no bucket. `retry_after(key, cost)` raises `ValueError` unless `cost > 0` and returns the key's `retry_after(cost)`; for a key with no bucket it is `0.0`, or `math.inf` when `cost` is more than `capacity`. Neither creates a bucket nor changes which key is most recently used.
12. `reset(key)` forgets the key and returns `True` if it had a bucket, `False` if not. The next `allow` for it starts with a full bucket.
13. `keys()` returns a new list of the tracked keys from least recently used to most recently used. `len(limiter)` is the number of tracked keys and `key in limiter` is whether the key has a bucket. None of these change the order.
