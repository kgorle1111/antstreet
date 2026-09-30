import pytest
from tokenbucket import TokenBucket


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_new_bucket_is_full():
    bucket = TokenBucket(rate=1, capacity=5, clock=Clock(100.0))
    assert bucket.available() == pytest.approx(5.0)
    assert isinstance(bucket.available(), float)


def test_allow_returns_bool_and_removes_cost():
    bucket = TokenBucket(rate=1, capacity=5, clock=Clock())
    assert bucket.allow() is True
    assert bucket.available() == pytest.approx(4.0)
    assert bucket.allow(3) is True
    assert bucket.available() == pytest.approx(1.0)


def test_bucket_drains_then_refuses():
    bucket = TokenBucket(rate=1, capacity=3, clock=Clock())
    assert [bucket.allow() for _ in range(5)] == [True, True, True, False, False]
    assert bucket.available() == pytest.approx(0.0)


def test_exactly_enough_tokens_is_enough():
    bucket = TokenBucket(rate=1, capacity=4, clock=Clock())
    assert bucket.allow(4) is True
    assert bucket.available() == pytest.approx(0.0)


def test_fractional_cost():
    bucket = TokenBucket(rate=1, capacity=2, clock=Clock())
    assert bucket.allow(0.5) is True
    assert bucket.allow(0.5) is True
    assert bucket.available() == pytest.approx(1.0)
    assert bucket.allow(1.5) is False
    assert bucket.available() == pytest.approx(1.0)


def test_reading_available_does_not_consume():
    bucket = TokenBucket(rate=1, capacity=2, clock=Clock())
    for _ in range(10):
        bucket.available()
    assert bucket.allow(2) is True


def test_float_capacity_and_rate():
    bucket = TokenBucket(rate=0.5, capacity=2.5, clock=Clock())
    assert bucket.available() == pytest.approx(2.5)
    assert bucket.allow(2.5) is True
    assert bucket.allow(0.5) is False
