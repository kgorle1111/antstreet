import pytest
from tokenbucket import TokenBucket


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_refill_is_proportional_to_elapsed_time():
    clock = Clock(10.0)
    bucket = TokenBucket(rate=2, capacity=10, clock=clock)
    assert bucket.allow(10) is True
    clock.now = 11.0
    assert bucket.available() == pytest.approx(2.0)
    clock.now = 13.0
    assert bucket.available() == pytest.approx(6.0)


def test_refill_is_continuous_not_in_whole_tokens():
    clock = Clock()
    bucket = TokenBucket(rate=2, capacity=10, clock=clock)
    assert bucket.allow(10) is True
    clock.now = 0.25
    assert bucket.available() == pytest.approx(0.5)
    assert bucket.allow(1) is False
    clock.now = 0.5
    assert bucket.available() == pytest.approx(1.0)
    assert bucket.allow(1) is True
    assert bucket.available() == pytest.approx(0.0)


def test_slow_rate_below_one_token_per_second():
    clock = Clock()
    bucket = TokenBucket(rate=0.25, capacity=4, clock=clock)
    assert bucket.allow(4) is True
    clock.now = 2.0
    assert bucket.available() == pytest.approx(0.5)
    assert bucket.allow(1) is False
    clock.now = 4.0
    assert bucket.allow(1) is True


def test_many_small_steps_add_up_like_one_big_step():
    clock = Clock()
    bucket = TokenBucket(rate=1, capacity=100, clock=clock)
    assert bucket.allow(100) is True
    for step in range(1, 41):
        clock.now = step * 0.5
        bucket.available()
    assert bucket.available() == pytest.approx(20.0)


def test_refill_after_partial_drain():
    clock = Clock()
    bucket = TokenBucket(rate=4, capacity=8, clock=clock)
    assert bucket.allow(6) is True
    clock.now = 0.5
    assert bucket.available() == pytest.approx(4.0)
    assert bucket.allow(4) is True
    clock.now = 1.0
    assert bucket.available() == pytest.approx(2.0)


def test_calls_at_the_same_instant_do_not_refill():
    clock = Clock(5.0)
    bucket = TokenBucket(rate=100, capacity=10, clock=clock)
    assert bucket.allow(10) is True
    assert bucket.allow() is False
    assert bucket.available() == pytest.approx(0.0)
