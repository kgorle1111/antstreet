import pytest
from tokenbucket import TokenBucket


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_going_backwards_does_not_remove_tokens():
    clock = Clock(100.0)
    bucket = TokenBucket(rate=1, capacity=10, clock=clock)
    assert bucket.allow(4) is True
    clock.now = 90.0
    assert bucket.available() == pytest.approx(6.0)
    assert bucket.allow(6) is True


def test_going_backwards_on_an_empty_bucket_stays_empty_not_negative():
    clock = Clock(100.0)
    bucket = TokenBucket(rate=1, capacity=10, clock=clock)
    assert bucket.allow(10) is True
    clock.now = 40.0
    assert bucket.available() == pytest.approx(0.0)
    assert bucket.allow() is False
    assert bucket.wait_time() == pytest.approx(1.0)


def test_going_backwards_adds_no_tokens():
    clock = Clock(100.0)
    bucket = TokenBucket(rate=1, capacity=10, clock=clock)
    assert bucket.allow(10) is True
    clock.now = 50.0
    assert bucket.allow() is False
    clock.now = 100.0
    assert bucket.available() == pytest.approx(0.0)
    assert bucket.allow() is False


def test_refill_resumes_from_the_latest_reading_seen():
    clock = Clock(100.0)
    bucket = TokenBucket(rate=1, capacity=10, clock=clock)
    assert bucket.allow(4) is True
    clock.now = 90.0
    assert bucket.available() == pytest.approx(6.0)
    clock.now = 102.0
    assert bucket.available() == pytest.approx(8.0)


def test_repeated_backwards_jumps_never_reduce_tokens():
    clock = Clock(1000.0)
    bucket = TokenBucket(rate=2, capacity=10, clock=clock)
    assert bucket.allow(10) is True
    clock.now = 1001.0
    before = bucket.available()
    assert before == pytest.approx(2.0)
    for now in (1000.5, 900.0, 0.0, -50.0, 1000.9):
        clock.now = now
        assert bucket.available() == pytest.approx(before)
    clock.now = 1002.0
    assert bucket.available() == pytest.approx(4.0)
