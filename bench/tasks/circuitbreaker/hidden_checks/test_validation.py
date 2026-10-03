import pytest
from circuitbreaker import CircuitBreaker


@pytest.mark.parametrize("n", [0, -1, -10])
def test_failure_threshold_below_one_raises(n):
    with pytest.raises(ValueError):
        CircuitBreaker(failure_threshold=n)


@pytest.mark.parametrize("t", [0, 0.0, -1, -0.5])
def test_non_positive_reset_timeout_raises(t):
    with pytest.raises(ValueError):
        CircuitBreaker(reset_timeout=t)


@pytest.mark.parametrize("n", [0, -1])
def test_half_open_successes_below_one_raises(n):
    with pytest.raises(ValueError):
        CircuitBreaker(half_open_successes=n)


def test_valid_extremes_are_accepted():
    CircuitBreaker(failure_threshold=1, reset_timeout=0.001, half_open_successes=1)
    CircuitBreaker(failure_threshold=1000, reset_timeout=1e9, half_open_successes=50)
