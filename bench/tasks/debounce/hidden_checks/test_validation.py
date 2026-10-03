import pytest
from debounce import Debouncer, Throttler


@pytest.mark.parametrize("wait", [0, 0.0, -1, -0.5])
def test_debouncer_needs_a_positive_wait(wait):
    with pytest.raises(ValueError):
        Debouncer(wait=wait)


@pytest.mark.parametrize("max_wait", [0, 1, 1.99, -3])
def test_max_wait_below_wait_raises(max_wait):
    with pytest.raises(ValueError):
        Debouncer(wait=2, max_wait=max_wait)


def test_valid_debouncers():
    Debouncer(wait=0.001)
    Debouncer(wait=2, max_wait=2)
    Debouncer(wait=2, max_wait=2.5)
    Debouncer(wait=2, max_wait=None)


@pytest.mark.parametrize("interval", [0, 0.0, -1, -0.5])
def test_throttler_needs_a_positive_interval(interval):
    with pytest.raises(ValueError):
        Throttler(interval=interval)
    with pytest.raises(ValueError):
        Throttler(interval=interval, trailing=False)


def test_valid_throttlers():
    Throttler(interval=0.001)
    Throttler(1, trailing=True)
    Throttler(1, False)


def test_instances_do_not_share_state():
    a, b = Debouncer(wait=1), Debouncer(wait=1)
    a.call(0, "a")
    assert b.pending() is False
    assert b.poll(10) == []
    t1, t2 = Throttler(interval=10), Throttler(interval=10)
    t1.call(0, "x")
    assert t2.call(1, "y") == ["y"]
