from bucket import TokenBucket
from registry import RateLimiter


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_keys_have_separate_buckets():
    limiter = RateLimiter(2, 1, clock=Clock())
    assert limiter.allow("a") is True
    assert limiter.allow("a") is True
    assert limiter.allow("a") is False
    assert limiter.allow("b") is True
    assert limiter.remaining("a") == 0
    assert limiter.remaining("b") == 1


def test_all_keys_share_the_clock():
    clock = Clock()
    limiter = RateLimiter(2, 1, clock=clock)
    for key in ("a", "b", "c"):
        limiter.allow(key, 2)
    clock.now = 1.5
    assert [limiter.remaining(k) for k in "abc"] == [1.5, 1.5, 1.5]


def test_keys_may_be_any_hashable_except_none():
    limiter = RateLimiter(1, 1, clock=Clock())
    for key in (0, 1.5, "", (1, 2), frozenset({1}), b"x", object):
        assert limiter.allow(key) is True
        assert limiter.allow(key) is False
    assert len(limiter) == 7


def test_equal_keys_are_the_same_key():
    limiter = RateLimiter(1, 1, clock=Clock())
    assert limiter.allow(("u", 1)) is True
    assert limiter.allow(("u", 1)) is False
    assert limiter.allow("u") is True
    assert len(limiter) == 2


def test_a_denied_call_creates_the_bucket_and_costs_nothing():
    limiter = RateLimiter(2, 1, clock=Clock())
    assert limiter.allow("big", 3) is False
    assert "big" in limiter
    assert limiter.remaining("big") == 2


def test_cost_is_taken_from_that_key_only():
    limiter = RateLimiter(10, 1, clock=Clock())
    assert limiter.allow("a", 7) is True
    assert limiter.allow("a", 4) is False
    assert limiter.allow("b", 10) is True
    assert limiter.remaining("a") == 3


def test_matches_a_standalone_bucket_per_key():
    clock = Clock()
    limiter = RateLimiter(3, 0.5, clock=clock)
    buckets = {k: TokenBucket(3, 0.5, clock=clock) for k in "xyz"}
    steps = [
        (0, "x", 2),
        (0, "y", 1),
        (1, "x", 2),
        (2, "z", 3),
        (2, "x", 1),
        (4, "x", 3),
        (9, "y", 3),
    ]
    for when, key, cost in steps:
        clock.now = when
        assert limiter.allow(key, cost) is buckets[key].try_acquire(cost)
    for key in "xyz":
        assert limiter.remaining(key) == buckets[key].available()
