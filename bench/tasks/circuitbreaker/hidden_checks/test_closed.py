from circuitbreaker import CircuitBreaker


def test_new_breaker_is_closed_and_allows():
    cb = CircuitBreaker(failure_threshold=3, reset_timeout=10)
    assert cb.state(0) == "closed"
    assert cb.allow(0) is True


def test_failures_below_threshold_stay_closed():
    cb = CircuitBreaker(failure_threshold=3, reset_timeout=10)
    cb.record_failure(1)
    cb.record_failure(2)
    assert cb.state(2) == "closed"
    assert cb.allow(2) is True


def test_reaching_threshold_opens():
    cb = CircuitBreaker(failure_threshold=3, reset_timeout=10)
    for t in (1, 2, 3):
        cb.record_failure(t)
    assert cb.state(3) == "open"
    assert cb.allow(3) is False


def test_threshold_of_one_opens_on_first_failure():
    cb = CircuitBreaker(failure_threshold=1, reset_timeout=5)
    cb.record_failure(0)
    assert cb.state(0) == "open"


def test_allow_and_state_do_not_count_as_failures():
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=10)
    for t in range(20):
        assert cb.allow(t) is True
        assert cb.state(t) == "closed"
    cb.record_failure(20)
    assert cb.state(20) == "closed"


def test_defaults_are_five_failures_and_thirty_seconds():
    cb = CircuitBreaker()
    for t in range(4):
        cb.record_failure(t)
    assert cb.state(4) == "closed"
    cb.record_failure(100)
    assert cb.state(100) == "open"
    assert cb.state(129.9) == "open"
    assert cb.state(130) == "half_open"
