from bucket import TokenBucket
from registry import RateLimiter


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_refills_at_the_given_rate():
    clock = Clock()
    bucket = TokenBucket(10, 2, clock=clock)
    assert bucket.try_acquire(10) is True
    clock.now = 1
    assert bucket.available() == 2
    clock.now = 2.5
    assert bucket.available() == 5
    assert bucket.try_acquire(5) is True
    assert bucket.available() == 0


def test_refill_is_capped_at_capacity():
    clock = Clock()
    bucket = TokenBucket(5, 1, clock=clock)
    assert bucket.try_acquire(2) is True
    clock.now = 1000
    assert bucket.available() == 5
    assert bucket.try_acquire(5) is True
    assert bucket.try_acquire(1) is False


def test_fractions_of_a_token_accumulate():
    clock = Clock()
    bucket = TokenBucket(2, 0.5, clock=clock)
    assert bucket.try_acquire(2) is True
    clock.now = 1
    assert bucket.available() == 0.5
    assert bucket.try_acquire() is False
    clock.now = 2
    assert bucket.try_acquire() is True
    assert bucket.available() == 0


def test_many_small_steps_equal_one_big_step():
    clock = Clock()
    stepped = TokenBucket(100, 4, clock=clock)
    jump_clock = Clock()
    jumped = TokenBucket(100, 4, clock=jump_clock)
    assert stepped.try_acquire(100) and jumped.try_acquire(100)
    for second in range(1, 11):
        clock.now = second
        stepped.available()
    jump_clock.now = 10
    assert stepped.available() == jumped.available() == 40


def test_refill_starts_from_the_clock_reading_at_construction():
    clock = Clock(100.0)
    bucket = TokenBucket(4, 1, clock=clock)
    assert bucket.try_acquire(4) is True
    clock.now = 101
    assert bucket.available() == 1
    clock.now = 103
    assert bucket.available() == 3


def test_failed_acquire_still_advances_the_refill_time():
    clock = Clock()
    bucket = TokenBucket(4, 1, clock=clock)
    assert bucket.try_acquire(4) is True
    clock.now = 1
    assert bucket.try_acquire(3) is False
    clock.now = 3
    assert bucket.available() == 3


def test_backwards_clock_neither_adds_nor_removes_tokens():
    clock = Clock(10.0)
    bucket = TokenBucket(5, 1, clock=clock)
    assert bucket.try_acquire(5) is True
    clock.now = 4.0
    assert bucket.available() == 0
    assert bucket.try_acquire() is False
    clock.now = 6.0  # measured from the earlier reading: two seconds have passed
    assert bucket.available() == 2


def test_backwards_clock_does_not_drain_a_partly_full_bucket():
    clock = Clock(10.0)
    bucket = TokenBucket(5, 1, clock=clock)
    bucket.try_acquire(3)
    clock.now = 0.0
    assert bucket.available() == 2
    clock.now = 1.0
    assert bucket.available() == 3


def test_limiter_buckets_refill_with_the_limiter_clock():
    clock = Clock()
    limiter = RateLimiter(2, 1, clock=clock)
    assert limiter.allow("a", 2) is True
    assert limiter.allow("a") is False
    clock.now = 1
    assert limiter.allow("a") is True
    assert limiter.allow("a") is False
