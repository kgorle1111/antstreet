from circuitbreaker import CircuitBreaker


def half_open(**kw):
    cb = CircuitBreaker(failure_threshold=1, reset_timeout=10, **kw)
    cb.record_failure(0)
    assert cb.state(10) == "half_open"
    return cb


def test_one_trial_at_a_time():
    cb = half_open()
    assert cb.allow(10) is True
    assert cb.allow(10) is False
    assert cb.allow(11) is False
    assert cb.state(11) == "half_open"


def test_successful_trial_closes_the_breaker():
    cb = half_open()
    assert cb.allow(10) is True
    cb.record_success(11)
    assert cb.state(11) == "closed"
    assert cb.allow(11) is True
    assert cb.allow(11) is True


def test_failed_trial_reopens_for_a_full_period():
    cb = half_open()
    assert cb.allow(10) is True
    cb.record_failure(12)
    assert cb.state(12) == "open"
    assert cb.allow(12) is False
    assert cb.state(21.9) == "open"
    assert cb.state(22) == "half_open"


def test_a_trial_is_allowed_again_after_the_period_following_a_failed_trial():
    cb = half_open()
    assert cb.allow(10) is True
    cb.record_failure(10)
    assert cb.allow(20) is True
    assert cb.allow(20) is False


def test_unreported_trial_blocks_forever():
    cb = half_open()
    assert cb.allow(10) is True
    assert cb.allow(1000) is False
    assert cb.state(1000) == "half_open"
