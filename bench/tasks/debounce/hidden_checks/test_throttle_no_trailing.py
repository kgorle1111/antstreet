from debounce import Throttler


def test_skipped_calls_are_dropped():
    t = Throttler(interval=10, trailing=False)
    assert t.call(0, "a") == ["a"]
    assert t.call(3, "b") == []
    assert t.pending() is False
    assert t.poll(10) == []
    assert t.poll(100) == []


def test_a_call_after_the_interval_runs_normally():
    t = Throttler(interval=10, trailing=False)
    t.call(0, "a")
    t.call(3, "b")
    assert t.call(10, "c") == ["c"]


def test_pending_is_never_true():
    t = Throttler(interval=10, trailing=False)
    for now in range(0, 40):
        t.call(now, now)
        assert t.pending() is False


def test_runs_only_at_interval_spacing_for_a_steady_stream():
    t = Throttler(interval=3, trailing=False)
    ran = []
    for now in range(0, 12):
        ran += t.call(now, now)
    assert ran == [0, 3, 6, 9]


def test_trailing_is_on_by_default():
    t = Throttler(interval=10)
    t.call(0, "a")
    t.call(1, "b")
    assert t.pending() is True
