from debounce import Debouncer


def test_a_continuous_burst_is_forced_out_at_max_wait():
    d = Debouncer(wait=2, max_wait=5)
    for t in range(5):
        d.call(t, f"v{t}")
        assert d.poll(t) == []
    assert d.poll(4.9) == []
    assert d.poll(5) == ["v4"]
    assert d.pending() is False


def test_max_wait_runs_from_the_start_of_the_burst():
    d = Debouncer(wait=2, max_wait=5)
    d.call(0, "a")
    d.call(1, "b")
    d.call(2, "c")
    d.call(3, "d")
    d.call(4, "e")
    assert d.poll(4) == []
    assert d.poll(5) == ["e"]


def test_after_a_forced_run_the_next_burst_starts_again():
    d = Debouncer(wait=2, max_wait=5)
    for t in range(5):
        d.call(t)
    assert d.poll(5) == [None]
    for t in range(6, 11):
        d.call(t, f"w{t}")
    assert d.poll(10) == []
    assert d.poll(10.9) == []
    assert d.poll(11) == ["w10"]


def test_without_max_wait_a_burst_is_never_forced():
    d = Debouncer(wait=2)
    for t in range(0, 1000):
        d.call(t, t)
        assert d.poll(t) == []
    assert d.poll(1002) == [999]


def test_max_wait_equal_to_wait_is_valid_and_fires_from_the_first_call():
    d = Debouncer(wait=2, max_wait=2)
    d.call(0, "a")
    d.call(1, "b")
    assert d.poll(1.5) == []
    assert d.poll(2) == ["b"]


def test_a_quiet_burst_fires_by_the_wait_before_max_wait():
    d = Debouncer(wait=2, max_wait=100)
    d.call(0, "a")
    assert d.poll(2) == ["a"]
