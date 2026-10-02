import pytest
from bucket import TokenBucket
from registry import RateLimiter


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_starts_full_and_drains():
    bucket = TokenBucket(3, 1, clock=Clock())
    assert bucket.available() == 3
    assert [bucket.try_acquire() for _ in range(4)] == [True, True, True, False]
    assert bucket.available() == 0


def test_acquire_several_at_once():
    bucket = TokenBucket(10, 1, clock=Clock())
    assert bucket.try_acquire(4) is True
    assert bucket.available() == 6
    assert bucket.try_acquire(6) is True
    assert bucket.available() == 0
    assert bucket.try_acquire(0.5) is False


def test_denied_acquire_removes_nothing():
    bucket = TokenBucket(5, 1, clock=Clock())
    assert bucket.try_acquire(3) is True
    assert bucket.try_acquire(3) is False
    assert bucket.available() == 2
    assert bucket.try_acquire(2) is True


def test_more_than_capacity_is_always_denied():
    bucket = TokenBucket(2, 100, clock=Clock())
    assert bucket.try_acquire(2.5) is False
    assert bucket.available() == 2


def test_available_does_not_consume_and_is_a_float():
    bucket = TokenBucket(4, 1, clock=Clock())
    assert bucket.available() == bucket.available() == 4
    assert isinstance(bucket.available(), float)


def test_fractional_costs():
    bucket = TokenBucket(1, 1, clock=Clock())
    assert bucket.try_acquire(0.25) is True
    assert bucket.try_acquire(0.5) is True
    assert bucket.try_acquire(0.5) is False
    assert bucket.available() == 0.25


def test_a_bucket_and_a_limiter_agree_on_the_same_script():
    clock = Clock()
    bucket = TokenBucket(4, 2, clock=clock)
    limiter = RateLimiter(4, 2, clock=clock)
    script = [(0, 3), (0, 3), (1, 1), (1, 3), (2.5, 4), (2.5, 1), (10, 4), (10, 0.5)]
    for when, cost in script:
        clock.now = when
        assert limiter.allow("k", cost) is bucket.try_acquire(cost)
        assert limiter.remaining("k") == bucket.available()


@pytest.mark.parametrize("n", [0, -1, -0.5])
def test_non_positive_requests_are_rejected(n):
    bucket = TokenBucket(2, 1, clock=Clock())
    with pytest.raises(ValueError):
        bucket.try_acquire(n)
    with pytest.raises(ValueError):
        bucket.retry_after(n)
    assert bucket.available() == 2
