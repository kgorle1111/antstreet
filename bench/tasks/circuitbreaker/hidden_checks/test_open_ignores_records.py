from circuitbreaker import CircuitBreaker


def opened():
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=10)
    cb.record_failure(0)
    cb.record_failure(0)
    return cb


def test_failure_while_open_does_not_restart_the_period():
    cb = opened()
    cb.record_failure(5)
    cb.record_failure(9)
    assert cb.state(10) == "half_open"


def test_success_while_open_does_not_close_it():
    cb = opened()
    cb.record_success(3)
    assert cb.state(3) == "open"
    assert cb.allow(3) is False
    assert cb.state(10) == "half_open"


def test_records_while_open_leave_a_clean_half_open_trial():
    cb = opened()
    cb.record_failure(4)
    cb.record_success(6)
    assert cb.allow(10) is True
    assert cb.state(10) == "half_open"
    assert cb.allow(10) is False
