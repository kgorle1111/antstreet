from registry import RateLimiter


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_remaining_of_an_unknown_key_is_full_capacity_and_creates_nothing():
    limiter = RateLimiter(7, 1, clock=Clock())
    assert limiter.remaining("ghost") == 7.0
    assert isinstance(limiter.remaining("ghost"), float)
    assert len(limiter) == 0
    assert "ghost" not in limiter
    assert limiter.keys() == []


def test_remaining_tracks_use_and_refill():
    clock = Clock()
    limiter = RateLimiter(4, 2, clock=clock)
    limiter.allow("k", 3)
    assert limiter.remaining("k") == 1
    clock.now = 1
    assert limiter.remaining("k") == 3
    clock.now = 100
    assert limiter.remaining("k") == 4


def test_reset_forgets_the_key_and_reports_whether_it_existed():
    limiter = RateLimiter(2, 0.001, clock=Clock())
    assert limiter.reset("k") is False
    limiter.allow("k", 2)
    assert limiter.allow("k") is False
    assert limiter.reset("k") is True
    assert "k" not in limiter
    assert len(limiter) == 0
    assert limiter.reset("k") is False
    assert limiter.allow("k", 2) is True


def test_reset_leaves_other_keys_and_their_order_alone():
    limiter = RateLimiter(2, 1, clock=Clock())
    for key in "abc":
        limiter.allow(key)
    limiter.reset("b")
    assert limiter.keys() == ["a", "c"]
    assert limiter.remaining("a") == 1


def test_reset_frees_a_slot_under_max_keys():
    limiter = RateLimiter(1, 1, clock=Clock(), max_keys=2)
    limiter.allow("a")
    limiter.allow("b")
    limiter.reset("a")
    limiter.allow("c")
    assert limiter.keys() == ["b", "c"]


def test_len_and_contains():
    limiter = RateLimiter(1, 1, clock=Clock())
    assert len(limiter) == 0
    limiter.allow("a")
    limiter.allow("a")
    limiter.allow("b")
    assert len(limiter) == 2
    assert "a" in limiter and "b" in limiter and "c" not in limiter
    assert None not in limiter
