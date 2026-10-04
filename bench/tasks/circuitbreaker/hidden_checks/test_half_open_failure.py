from circuitbreaker import CircuitBreaker


def test_failure_in_half_open_restarts_the_period_from_that_time():
    cb = CircuitBreaker(failure_threshold=1, reset_timeout=10)
    cb.record_failure(0)
    assert cb.allow(15) is True
    cb.record_failure(15)
    assert cb.state(24) == "open"
    assert cb.state(25) == "half_open"


def test_failure_in_half_open_without_asking_first_also_reopens():
    cb = CircuitBreaker(failure_threshold=1, reset_timeout=10)
    cb.record_failure(0)
    cb.record_failure(10)
    assert cb.state(10) == "open"
    assert cb.state(19.9) == "open"
    assert cb.state(20) == "half_open"


def test_repeated_failed_trials_keep_pushing_the_period_out():
    cb = CircuitBreaker(failure_threshold=1, reset_timeout=10)
    cb.record_failure(0)
    t = 10
    for _ in range(3):
        assert cb.state(t) == "half_open"
        assert cb.allow(t) is True
        cb.record_failure(t)
        assert cb.state(t + 9) == "open"
        t += 10
    assert cb.state(t) == "half_open"
