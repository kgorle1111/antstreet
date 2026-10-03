from debounce import Throttler


def test_a_call_after_the_interval_runs_and_drops_the_waiting_value():
    t = Throttler(interval=10)
    assert t.call(0, "a") == ["a"]
    assert t.call(3, "b") == []
    assert t.call(12, "c") == ["c"]
    assert t.pending() is False
    assert t.poll(30) == []


def test_the_superseded_value_never_runs():
    t = Throttler(interval=10)
    ran = []
    ran += t.call(0, "a")
    ran += t.call(3, "b")
    ran += t.call(10, "c")
    ran += t.poll(20)
    ran += t.poll(40)
    assert ran == ["a", "c"]


def test_a_waiting_value_is_kept_when_polled_too_early_and_called_early_again():
    t = Throttler(interval=10)
    t.call(0, "a")
    t.call(2, "b")
    assert t.poll(5) == []
    t.call(7, "c")
    assert t.pending() is True
    assert t.poll(10) == ["c"]


def test_a_steady_stream_with_polling_runs_once_per_interval():
    t = Throttler(interval=3)
    ran = []
    for now in range(0, 13):
        ran += t.call(now, now)
        ran += t.poll(now)
    assert ran == [0, 3, 6, 9, 12]
