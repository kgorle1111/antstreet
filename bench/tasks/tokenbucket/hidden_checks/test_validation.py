import pytest
from tokenbucket import TokenBucket


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


@pytest.mark.parametrize("rate", [0, 0.0, -1, -0.5])
def test_non_positive_rate_raises(rate):
    with pytest.raises(ValueError):
        TokenBucket(rate=rate, capacity=5, clock=Clock())


@pytest.mark.parametrize("capacity", [0, 0.0, -1, -0.5])
def test_non_positive_capacity_raises(capacity):
    with pytest.raises(ValueError):
        TokenBucket(rate=1, capacity=capacity, clock=Clock())


@pytest.mark.parametrize("cost", [0, 0.0, -1, -0.5])
def test_non_positive_cost_raises(cost):
    bucket = TokenBucket(rate=1, capacity=5, clock=Clock())
    with pytest.raises(ValueError):
        bucket.allow(cost)
    with pytest.raises(ValueError):
        bucket.wait_time(cost)


def test_bad_cost_does_not_change_the_bucket():
    bucket = TokenBucket(rate=1, capacity=5, clock=Clock())
    with pytest.raises(ValueError):
        bucket.allow(-3)
    assert bucket.available() == pytest.approx(5.0)


def test_valid_small_and_fractional_arguments_are_accepted():
    bucket = TokenBucket(rate=0.001, capacity=0.5, clock=Clock())
    assert bucket.allow(0.25) is True
    assert bucket.wait_time(0.5) > 0.0
    TokenBucket(rate=1000, capacity=1, clock=Clock())
