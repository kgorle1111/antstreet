import pytest
from tokenbucket import TokenBucket


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_full_bucket_does_not_grow_while_idle():
    clock = Clock()
    bucket = TokenBucket(rate=5, capacity=10, clock=clock)
    clock.now = 1000.0
    assert bucket.available() == pytest.approx(10.0)


def test_refill_stops_at_capacity():
    clock = Clock()
    bucket = TokenBucket(rate=2, capacity=10, clock=clock)
    assert bucket.allow(4) is True
    clock.now = 100.0
    assert bucket.available() == pytest.approx(10.0)


def test_idle_time_is_not_banked_beyond_capacity():
    clock = Clock()
    bucket = TokenBucket(rate=1, capacity=3, clock=clock)
    clock.now = 500.0
    assert [bucket.allow() for _ in range(5)] == [True, True, True, False, False]


def test_allow_full_capacity_after_long_idle_only_once():
    clock = Clock()
    bucket = TokenBucket(rate=1, capacity=4, clock=clock)
    assert bucket.allow(4) is True
    clock.now = 10_000.0
    assert bucket.allow(4) is True
    assert bucket.allow(1) is False


def test_cap_applies_before_the_next_refill_step():
    clock = Clock()
    bucket = TokenBucket(rate=1, capacity=5, clock=clock)
    assert bucket.allow(5) is True
    clock.now = 50.0
    assert bucket.available() == pytest.approx(5.0)
    assert bucket.allow(5) is True
    clock.now = 52.0
    assert bucket.available() == pytest.approx(2.0)
