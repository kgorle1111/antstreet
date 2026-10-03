from circuitbreaker import CircuitBreaker


def half_open(n):
    cb = CircuitBreaker(failure_threshold=1, reset_timeout=10, half_open_successes=n)
    cb.record_failure(0)
    return cb


def test_needs_the_configured_number_of_trials():
    cb = half_open(3)
    for t in (10, 11):
        assert cb.allow(t) is True
        cb.record_success(t)
        assert cb.state(t) == "half_open"
    assert cb.allow(12) is True
    cb.record_success(12)
    assert cb.state(12) == "closed"


def test_next_trial_waits_for_the_previous_one_to_be_reported():
    cb = half_open(2)
    assert cb.allow(10) is True
    assert cb.allow(10) is False
    cb.record_success(10)
    assert cb.allow(10) is True
    assert cb.allow(10) is False


def test_failure_discards_the_successes_counted_so_far():
    cb = half_open(2)
    assert cb.allow(10) is True
    cb.record_success(10)
    assert cb.allow(10) is True
    cb.record_failure(11)
    assert cb.state(11) == "open"
    assert cb.allow(21) is True
    cb.record_success(21)
    assert cb.state(21) == "half_open"
    assert cb.allow(21) is True
    cb.record_success(21)
    assert cb.state(21) == "closed"


def test_default_needs_a_single_success():
    cb = CircuitBreaker(failure_threshold=1, reset_timeout=1)
    cb.record_failure(0)
    assert cb.allow(1) is True
    cb.record_success(1)
    assert cb.state(1) == "closed"
