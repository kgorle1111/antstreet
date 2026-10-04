from circuitbreaker import CircuitBreaker


def opened(timeout=10.0, at=100.0):
    cb = CircuitBreaker(failure_threshold=1, reset_timeout=timeout)
    cb.record_failure(at)
    return cb


def test_open_just_before_the_timeout():
    cb = opened()
    assert cb.state(109.9) == "open"
    assert cb.allow(109.9) is False


def test_half_open_at_exactly_the_timeout():
    cb = opened()
    assert cb.state(110) == "half_open"


def test_half_open_stays_half_open_as_time_passes():
    cb = opened()
    assert cb.state(110) == "half_open"
    assert cb.state(500) == "half_open"


def test_allow_while_open_does_not_move_the_timer():
    cb = opened()
    for t in (101, 105, 109):
        assert cb.allow(t) is False
    assert cb.state(110) == "half_open"


def test_fractional_timeout():
    cb = opened(timeout=0.25, at=1.0)
    assert cb.state(1.2) == "open"
    assert cb.state(1.25) == "half_open"
