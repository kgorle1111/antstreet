import pytest
from registry import RateLimiter


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_oldest_unused_key_is_forgotten_first():
    limiter = RateLimiter(1, 1, clock=Clock(), max_keys=2)
    limiter.allow("a")
    limiter.allow("b")
    limiter.allow("c")
    assert limiter.keys() == ["b", "c"]
    assert len(limiter) == 2
    assert "a" not in limiter


def test_allow_on_a_tracked_key_makes_it_most_recent():
    limiter = RateLimiter(5, 1, clock=Clock(), max_keys=2)
    limiter.allow("a")
    limiter.allow("b")
    limiter.allow("a")
    assert limiter.keys() == ["b", "a"]
    limiter.allow("c")
    assert limiter.keys() == ["a", "c"]


def test_a_denied_allow_counts_as_a_use():
    limiter = RateLimiter(1, 1, clock=Clock(), max_keys=2)
    limiter.allow("a")
    limiter.allow("b")
    assert limiter.allow("a") is False
    limiter.allow("c")
    assert limiter.keys() == ["a", "c"]


def test_reading_does_not_change_recency():
    limiter = RateLimiter(2, 1, clock=Clock(), max_keys=2)
    limiter.allow("a")
    limiter.allow("b")
    limiter.remaining("a")
    limiter.retry_after("a")
    len(limiter)
    limiter.keys()
    assert "a" in limiter
    limiter.allow("c")
    assert limiter.keys() == ["b", "c"]


def test_forgotten_key_comes_back_with_a_full_bucket():
    clock = Clock()
    limiter = RateLimiter(2, 0.001, clock=clock, max_keys=1)
    assert limiter.allow("a", 2) is True
    assert limiter.allow("a") is False
    limiter.allow("b")
    assert limiter.allow("a", 2) is True


def test_unknown_key_reads_do_not_take_a_slot():
    limiter = RateLimiter(2, 1, clock=Clock(), max_keys=1)
    limiter.allow("a")
    assert limiter.remaining("ghost") == 2.0
    assert limiter.retry_after("ghost") == 0.0
    assert limiter.keys() == ["a"]


def test_max_keys_one_keeps_only_the_latest():
    limiter = RateLimiter(1, 1, clock=Clock(), max_keys=1)
    for key in "abcde":
        limiter.allow(key)
    assert limiter.keys() == ["e"]


def test_without_max_keys_nothing_is_forgotten():
    limiter = RateLimiter(1, 1, clock=Clock())
    for n in range(500):
        limiter.allow(n)
    assert len(limiter) == 500
    assert limiter.keys() == list(range(500))


def test_keys_returns_a_copy():
    limiter = RateLimiter(1, 1, clock=Clock())
    limiter.allow("a")
    snapshot = limiter.keys()
    snapshot.append("zzz")
    assert limiter.keys() == ["a"]
    assert "zzz" not in limiter


@pytest.mark.parametrize("max_keys", [0, -1, 1.5, True, "3"])
def test_bad_max_keys(max_keys):
    with pytest.raises(ValueError):
        RateLimiter(1, 1, clock=Clock(), max_keys=max_keys)
