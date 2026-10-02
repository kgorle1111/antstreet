from bucket import TokenBucket
from registry import RateLimiter


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_burst_then_steady_rate():
    clock = Clock()
    limiter = RateLimiter(5, 1, clock=clock)
    assert sum(limiter.allow("u") for _ in range(100)) == 5
    allowed = 0
    for step in range(1, 21):
        clock.now = step * 0.5
        allowed += limiter.allow("u")
    assert allowed == 10


def test_interleaved_clients_do_not_steal_from_each_other():
    clock = Clock()
    limiter = RateLimiter(2, 1, clock=clock)
    results = {"a": [], "b": []}
    for step in range(8):
        clock.now = step
        for key in ("a", "b"):
            results[key].append(limiter.allow(key, 2 if key == "a" else 1))
    assert results["b"] == [True] * 8
    assert results["a"] == [True, False, True, False, True, False, True, False]


def test_idle_time_never_banks_more_than_capacity():
    clock = Clock()
    limiter = RateLimiter(3, 10, clock=clock)
    limiter.allow("k", 3)
    clock.now = 3600
    assert sum(limiter.allow("k") for _ in range(10)) == 3


def test_retry_after_is_consistent_with_allow_over_a_long_run():
    clock = Clock()
    limiter = RateLimiter(4, 2, clock=clock)
    denied_then_waited = 0
    for _ in range(50):
        if not limiter.allow("k", 3):
            wait = limiter.retry_after("k", 3)
            assert 0 < wait <= 1.5
            clock.now += wait
            assert limiter.allow("k", 3) is True
            denied_then_waited += 1
        clock.now += 0.25
    assert denied_then_waited > 10


def test_limiter_with_eviction_under_many_keys_never_exceeds_max():
    clock = Clock()
    limiter = RateLimiter(2, 1, clock=clock, max_keys=10)
    for n in range(1000):
        clock.now += 0.01
        limiter.allow(n % 37)
        assert len(limiter) <= 10
    assert len(limiter) == 10


def test_standalone_bucket_and_limiter_share_semantics_for_retry_after():
    clock = Clock()
    bucket = TokenBucket(6, 3, clock=clock)
    limiter = RateLimiter(6, 3, clock=clock)
    for cost in (4, 4, 2):
        assert limiter.allow("k", cost) is bucket.try_acquire(cost)
        for ask in (1, 3, 6, 7):
            assert limiter.retry_after("k", ask) == bucket.retry_after(ask)
        clock.now += 0.5
