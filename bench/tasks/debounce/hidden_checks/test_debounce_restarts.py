from debounce import Debouncer


def test_every_call_restarts_the_wait():
    d = Debouncer(wait=2)
    for t in range(5):
        d.call(t, f"v{t}")
    assert d.poll(5) == []
    assert d.poll(5.9) == []
    assert d.poll(6) == ["v4"]


def test_polling_in_between_does_not_disturb_the_wait():
    d = Debouncer(wait=3)
    d.call(0, "a")
    assert d.poll(1) == []
    assert d.poll(2) == []
    d.call(2.5, "b")
    assert d.poll(4) == []
    assert d.poll(5) == []
    assert d.poll(5.5) == ["b"]


def test_a_call_just_before_the_deadline_pushes_it_out():
    d = Debouncer(wait=2)
    d.call(0, "a")
    d.call(1.75, "b")
    assert d.poll(2) == []
    assert d.poll(3.5) == []
    assert d.poll(3.75) == ["b"]


def test_a_burst_with_gaps_shorter_than_the_wait_is_one_event():
    d = Debouncer(wait=10)
    fired = []
    for t in range(0, 100, 9):
        d.call(t, t)
        fired += d.poll(t)
    assert fired == []
    assert d.poll(200) == [99]
