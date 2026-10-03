from debounce import Debouncer


def test_nothing_is_waiting_at_first():
    d = Debouncer(wait=2)
    assert d.pending() is False
    assert d.poll(100) == []


def test_a_call_fires_once_the_wait_has_passed():
    d = Debouncer(wait=2)
    d.call(0, "a")
    assert d.pending() is True
    assert d.poll(1.5) == []
    assert d.pending() is True
    assert d.poll(2.5) == ["a"]
    assert d.pending() is False


def test_it_fires_only_once():
    d = Debouncer(wait=2)
    d.call(0, "a")
    assert d.poll(5) == ["a"]
    assert d.poll(6) == []
    assert d.poll(1000) == []


def test_poll_returns_a_list():
    d = Debouncer(wait=1)
    d.call(0, 7)
    got = d.poll(1)
    assert isinstance(got, list)
    assert got == [7]
    assert isinstance(d.poll(2), list)


def test_a_new_call_after_firing_is_a_new_burst():
    d = Debouncer(wait=2)
    d.call(0, "a")
    assert d.poll(2) == ["a"]
    d.call(10, "b")
    assert d.poll(11) == []
    assert d.poll(12) == ["b"]


def test_call_returns_none():
    assert Debouncer(wait=1).call(0, "x") is None


def test_the_latest_value_wins():
    d = Debouncer(wait=2)
    d.call(0, "a")
    d.call(0.5, "b")
    d.call(1, "c")
    assert d.poll(10) == ["c"]


def test_none_is_a_value_like_any_other():
    d = Debouncer(wait=1)
    d.call(0)
    assert d.poll(5) == [None]
    d.call(10, None)
    assert d.poll(20) == [None]
    assert d.poll(30) == []


def test_a_later_call_without_a_value_replaces_an_earlier_value():
    d = Debouncer(wait=1)
    d.call(0, "a")
    d.call(0.5)
    assert d.poll(10) == [None]


def test_values_can_be_any_object():
    d = Debouncer(wait=1)
    payload = {"k": [1, 2, 3]}
    d.call(0, payload)
    (got,) = d.poll(1)
    assert got is payload


def test_each_burst_has_its_own_value():
    d = Debouncer(wait=1)
    d.call(0, "x")
    assert d.poll(1) == ["x"]
    d.call(5, "y")
    assert d.poll(6) == ["y"]
