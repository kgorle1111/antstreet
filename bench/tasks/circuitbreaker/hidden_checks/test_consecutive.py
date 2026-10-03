from circuitbreaker import CircuitBreaker


def test_success_resets_the_failure_count():
    cb = CircuitBreaker(failure_threshold=3, reset_timeout=10)
    cb.record_failure(0)
    cb.record_failure(1)
    cb.record_success(2)
    cb.record_failure(3)
    cb.record_failure(4)
    assert cb.state(4) == "closed"
    cb.record_failure(5)
    assert cb.state(5) == "open"


def test_alternating_results_never_open():
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=10)
    for t in range(0, 40, 2):
        cb.record_failure(t)
        cb.record_success(t + 1)
    assert cb.state(40) == "closed"
    assert cb.allow(40) is True


def test_success_on_a_fresh_breaker_changes_nothing():
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=10)
    cb.record_success(0)
    cb.record_failure(1)
    assert cb.state(1) == "closed"
    cb.record_failure(2)
    assert cb.state(2) == "open"


def test_the_opening_time_is_the_time_of_the_last_failure():
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=10)
    cb.record_failure(0)
    cb.record_failure(7)
    assert cb.state(16.9) == "open"
    assert cb.state(17) == "half_open"
