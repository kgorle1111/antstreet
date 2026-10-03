from circuitbreaker import CircuitBreaker


def test_closed_again_needs_a_fresh_run_of_failures():
    cb = CircuitBreaker(failure_threshold=3, reset_timeout=10)
    for t in (0, 1, 2):
        cb.record_failure(t)
    assert cb.allow(12) is True
    cb.record_success(12)
    assert cb.state(12) == "closed"
    cb.record_failure(13)
    cb.record_failure(14)
    assert cb.state(14) == "closed"
    cb.record_failure(15)
    assert cb.state(15) == "open"


def test_failures_before_a_trip_do_not_leak_into_the_next_closed_period():
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=5)
    cb.record_failure(0)
    cb.record_failure(1)
    assert cb.allow(6) is True
    cb.record_success(6)
    cb.record_failure(7)
    assert cb.state(7) == "closed"


def test_two_full_cycles():
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=10, half_open_successes=2)
    now = 0
    for _ in range(2):
        cb.record_failure(now)
        cb.record_failure(now)
        assert cb.state(now) == "open"
        now += 10
        for _ in range(2):
            assert cb.allow(now) is True
            cb.record_success(now)
        assert cb.state(now) == "closed"
        now += 1


def test_independent_breakers_do_not_share_state():
    a = CircuitBreaker(failure_threshold=1, reset_timeout=10)
    b = CircuitBreaker(failure_threshold=1, reset_timeout=10)
    a.record_failure(0)
    assert a.state(0) == "open"
    assert b.state(0) == "closed"
