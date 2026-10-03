from debounce import Debouncer


def test_exactly_the_wait_fires():
    d = Debouncer(wait=1)
    d.call(10, "a")
    assert d.poll(10.5) == []
    assert d.poll(11) == ["a"]


def test_just_before_the_wait_does_not_fire():
    d = Debouncer(wait=1)
    d.call(10, "a")
    assert d.poll(10.99) == []


def test_fractional_wait():
    d = Debouncer(wait=0.25)
    d.call(1.0, "a")
    assert d.poll(1.125) == []
    assert d.poll(1.25) == ["a"]


def test_a_call_at_the_same_instant_as_the_previous_one():
    d = Debouncer(wait=1)
    d.call(5, "a")
    d.call(5, "b")
    assert d.poll(5.5) == []
    assert d.poll(6) == ["b"]


def test_polling_at_the_time_of_the_call_does_not_fire():
    d = Debouncer(wait=1)
    d.call(5, "a")
    assert d.poll(5) == []
    assert d.pending() is True
