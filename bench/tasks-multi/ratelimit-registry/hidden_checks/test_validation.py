import pytest
from bucket import TokenBucket
from registry import RateLimiter


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


@pytest.mark.parametrize("bad", [0, -1, -0.5])
def test_bucket_rejects_bad_capacity_and_rate(bad):
    with pytest.raises(ValueError):
        TokenBucket(bad, 1, clock=Clock())
    with pytest.raises(ValueError):
        TokenBucket(1, bad, clock=Clock())


@pytest.mark.parametrize("bad", [0, -1, -0.5])
def test_limiter_rejects_bad_capacity_and_rate(bad):
    with pytest.raises(ValueError):
        RateLimiter(bad, 1, clock=Clock())
    with pytest.raises(ValueError):
        RateLimiter(1, bad, clock=Clock())


def test_tiny_but_positive_values_are_fine():
    bucket = TokenBucket(0.5, 0.001, clock=Clock())
    assert bucket.available() == 0.5
    assert bucket.try_acquire(0.5) is True


@pytest.mark.parametrize("cost", [0, -1, -0.25])
def test_limiter_rejects_bad_cost_before_doing_anything(cost):
    limiter = RateLimiter(2, 1, clock=Clock(), max_keys=1)
    limiter.allow("keep")
    with pytest.raises(ValueError):
        limiter.allow("new", cost)
    with pytest.raises(ValueError):
        limiter.retry_after("new", cost)
    with pytest.raises(ValueError):
        limiter.retry_after("keep", cost)
    assert limiter.keys() == ["keep"]
    assert limiter.remaining("keep") == 1


def test_none_is_not_a_key():
    limiter = RateLimiter(2, 1, clock=Clock())
    with pytest.raises(ValueError):
        limiter.allow(None)
    with pytest.raises(ValueError):
        limiter.remaining(None)
    with pytest.raises(ValueError):
        limiter.retry_after(None)
    with pytest.raises(ValueError):
        limiter.reset(None)
    assert len(limiter) == 0


def test_the_default_clock_works_without_injection():
    limiter = RateLimiter(2, 1)
    assert limiter.allow("a") is True
    assert limiter.allow("a") is True
    assert limiter.allow("a") is False
    bucket = TokenBucket(2, 1)
    assert bucket.available() == pytest.approx(2.0, abs=0.5)
