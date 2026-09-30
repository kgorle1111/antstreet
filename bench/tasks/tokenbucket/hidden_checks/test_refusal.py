import pytest
from tokenbucket import TokenBucket


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_refused_allow_removes_nothing():
    bucket = TokenBucket(rate=1, capacity=10, clock=Clock())
    assert bucket.allow(4) is True
    assert bucket.allow(7) is False
    assert bucket.available() == pytest.approx(6.0)
    assert bucket.allow(6) is True


def test_refusal_does_not_lose_refill_progress():
    clock = Clock()
    bucket = TokenBucket(rate=1, capacity=10, clock=clock)
    assert bucket.allow(10) is True
    clock.now = 0.5
    assert bucket.allow(1) is False
    clock.now = 1.0
    assert bucket.allow(1) is True


def test_repeated_refusals_do_not_stall_the_bucket():
    clock = Clock()
    bucket = TokenBucket(rate=1, capacity=10, clock=clock)
    assert bucket.allow(10) is True
    for step in range(1, 5):
        clock.now = step * 0.25
        assert bucket.allow(2) is False
    clock.now = 2.0
    assert bucket.allow(2) is True


def test_cost_above_capacity_is_refused_without_error():
    bucket = TokenBucket(rate=1, capacity=5, clock=Clock())
    assert bucket.allow(5.5) is False
    assert bucket.allow(100) is False
    assert bucket.available() == pytest.approx(5.0)


def test_refusal_leaves_a_later_cheaper_request_possible():
    bucket = TokenBucket(rate=1, capacity=5, clock=Clock())
    assert bucket.allow(3) is True
    assert bucket.allow(3) is False
    assert bucket.allow(2) is True
    assert bucket.allow(1) is False
