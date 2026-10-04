from debounce import Debouncer


def test_cancel_drops_the_waiting_call():
    d = Debouncer(wait=2)
    d.call(0, "a")
    d.cancel()
    assert d.pending() is False
    assert d.poll(100) == []


def test_cancel_with_nothing_waiting_does_nothing():
    d = Debouncer(wait=2)
    assert d.cancel() is None
    d.cancel()
    assert d.pending() is False
    d.call(0, "a")
    assert d.poll(2) == ["a"]


def test_a_call_after_cancel_works_normally():
    d = Debouncer(wait=2)
    d.call(0, "a")
    d.cancel()
    d.call(200, "b")
    assert d.pending() is True
    assert d.poll(201) == []
    assert d.poll(202) == ["b"]


def test_cancel_starts_a_new_burst_for_max_wait():
    d = Debouncer(wait=2, max_wait=5)
    d.call(0, "a")
    d.call(1, "b")
    d.cancel()
    d.call(4, "x")
    assert d.poll(5) == []
    assert d.poll(6) == ["x"]


def test_cancel_after_firing_changes_nothing():
    d = Debouncer(wait=1)
    d.call(0, "a")
    assert d.poll(1) == ["a"]
    d.cancel()
    d.call(5, "b")
    assert d.poll(6) == ["b"]
