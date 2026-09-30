import pytest
from tokenbucket import TokenBucket


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_wait_time_is_zero_when_tokens_are_available():
    bucket = TokenBucket(rate=1, capacity=5, clock=Clock())
    assert bucket.wait_time() == 0.0
    assert bucket.wait_time(5) == 0.0
    assert isinstance(bucket.wait_time(), float)


def test_wait_time_for_an_empty_bucket():
    bucket = TokenBucket(rate=2, capacity=10, clock=Clock())
    assert bucket.allow(10) is True
    assert bucket.wait_time() == pytest.approx(0.5)
    assert bucket.wait_time(4) == pytest.approx(2.0)
    assert bucket.wait_time(10) == pytest.approx(5.0)


def test_wait_time_accounts_for_tokens_already_held():
    bucket = TokenBucket(rate=2, capacity=10, clock=Clock())
    assert bucket.allow(7) is True
    assert bucket.wait_time(5) == pytest.approx(1.0)
    assert bucket.wait_time(3) == pytest.approx(0.0)


def test_wait_time_accounts_for_elapsed_time():
    clock = Clock()
    bucket = TokenBucket(rate=2, capacity=10, clock=clock)
    assert bucket.allow(10) is True
    clock.now = 0.25
    assert bucket.wait_time() == pytest.approx(0.25)
    clock.now = 0.5
    assert bucket.wait_time() == 0.0


def test_waiting_that_long_makes_allow_succeed():
    clock = Clock(50.0)
    bucket = TokenBucket(rate=4, capacity=8, clock=clock)
    assert bucket.allow(8) is True
    wait = bucket.wait_time(6)
    assert wait == pytest.approx(1.5)
    clock.now += wait
    assert bucket.allow(6) is True
    assert bucket.available() == pytest.approx(0.0)


def test_wait_time_does_not_consume_tokens():
    clock = Clock()
    bucket = TokenBucket(rate=1, capacity=5, clock=clock)
    assert bucket.allow(3) is True
    for _ in range(5):
        bucket.wait_time(4)
    assert bucket.available() == pytest.approx(2.0)


def test_wait_time_for_exactly_capacity():
    bucket = TokenBucket(rate=0.5, capacity=4, clock=Clock())
    assert bucket.allow(4) is True
    assert bucket.wait_time(4) == pytest.approx(8.0)


def test_cost_above_capacity_raises():
    bucket = TokenBucket(rate=1, capacity=5, clock=Clock())
    with pytest.raises(ValueError):
        bucket.wait_time(5.5)
    with pytest.raises(ValueError):
        bucket.wait_time(100)
