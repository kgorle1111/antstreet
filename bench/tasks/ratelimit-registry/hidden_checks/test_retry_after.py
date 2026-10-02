import math

from bucket import TokenBucket
from registry import RateLimiter


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_zero_when_available_now():
    bucket = TokenBucket(5, 1, clock=Clock())
    assert bucket.retry_after() == 0.0
    assert bucket.retry_after(5) == 0.0
    assert isinstance(bucket.retry_after(), float)


def test_seconds_until_enough_tokens():
    clock = Clock()
    bucket = TokenBucket(10, 2, clock=clock)
    bucket.try_acquire(10)
    assert bucket.retry_after(1) == 0.5
    assert bucket.retry_after(4) == 2.0
    assert bucket.retry_after(10) == 5.0
    clock.now = 1
    assert bucket.retry_after(4) == 1.0
    clock.now = 2
    assert bucket.retry_after(4) == 0.0


def test_partial_tokens_count():
    bucket = TokenBucket(4, 1, clock=Clock())
    bucket.try_acquire(2.5)
    assert bucket.retry_after(2) == 0.5
    assert bucket.retry_after(4) == 2.5


def test_infinite_when_more_than_capacity():
    bucket = TokenBucket(3, 1, clock=Clock())
    assert bucket.retry_after(3.5) == math.inf
    assert bucket.retry_after(3) == 0.0


def test_retry_after_does_not_consume():
    clock = Clock()
    bucket = TokenBucket(2, 1, clock=clock)
    bucket.try_acquire(2)
    first = bucket.retry_after(2)
    assert first == bucket.retry_after(2) == 2.0
    assert bucket.available() == 0
    clock.now = first
    assert bucket.try_acquire(2) is True


def test_limiter_retry_after_for_known_and_unknown_keys():
    clock = Clock()
    limiter = RateLimiter(4, 2, clock=clock)
    assert limiter.retry_after("new") == 0.0
    assert limiter.retry_after("new", 4) == 0.0
    assert limiter.retry_after("new", 4.5) == math.inf
    assert len(limiter) == 0
    limiter.allow("k", 4)
    assert limiter.retry_after("k") == 0.5
    assert limiter.retry_after("k", 4) == 2.0
    assert limiter.retry_after("k", 5) == math.inf
    clock.now = 1
    assert limiter.retry_after("k", 4) == 1.0
    assert limiter.retry_after("other") == 0.0


def test_waiting_the_advised_time_makes_allow_succeed():
    clock = Clock()
    limiter = RateLimiter(4, 2, clock=clock)
    assert limiter.allow("k", 4) is True
    wait = limiter.retry_after("k", 2)
    assert wait == 1.0
    clock.now = wait
    assert limiter.allow("k", 2) is True
