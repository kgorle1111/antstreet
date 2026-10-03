from debounce import Throttler


def test_the_latest_skipped_value_runs_when_the_interval_is_up():
    t = Throttler(interval=10)
    assert t.call(0, "a") == ["a"]
    assert t.call(3, "b") == []
    assert t.call(6, "c") == []
    assert t.pending() is True
    assert t.poll(9) == []
    assert t.poll(10) == ["c"]
    assert t.pending() is False
    assert t.poll(11) == []


def test_a_trailing_run_restarts_the_interval_from_the_poll_time():
    t = Throttler(interval=10)
    t.call(0, "a")
    t.call(3, "b")
    assert t.poll(12) == ["b"]
    assert t.call(15, "c") == []
    assert t.poll(21) == []
    assert t.poll(22) == ["c"]
    assert t.call(31, "d") == []
    assert t.call(32, "e") == ["e"]


def test_nothing_trails_when_only_the_first_call_was_made():
    t = Throttler(interval=10)
    t.call(0, "a")
    assert t.pending() is False
    assert t.poll(10) == []
    assert t.poll(50) == []


def test_pending_is_false_at_first():
    t = Throttler(interval=1)
    assert t.pending() is False
    assert t.poll(5) == []


def test_a_waiting_value_replaces_an_earlier_waiting_value():
    t = Throttler(interval=10)
    t.call(0, "a")
    t.call(1, "b")
    t.call(2, None)
    assert t.poll(10) == [None]


def test_a_leading_run_after_a_trailing_one():
    t = Throttler(interval=4)
    t.call(0, "a")
    t.call(1, "b")
    assert t.poll(4) == ["b"]
    assert t.call(8, "c") == ["c"]
