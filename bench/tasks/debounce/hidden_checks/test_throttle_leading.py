from debounce import Throttler


def test_the_first_call_runs_at_once_even_at_time_zero():
    t = Throttler(interval=10)
    assert t.call(0, "a") == ["a"]


def test_calls_inside_the_interval_do_not_run():
    t = Throttler(interval=10, trailing=False)
    assert t.call(0, "a") == ["a"]
    assert t.call(1, "b") == []
    assert t.call(9.5, "c") == []


def test_exactly_the_interval_later_runs_again():
    t = Throttler(interval=10, trailing=False)
    assert t.call(0, "a") == ["a"]
    assert t.call(10, "b") == ["b"]
    assert t.call(19.9, "c") == []
    assert t.call(20, "d") == ["d"]


def test_the_first_call_may_come_at_any_time():
    t = Throttler(interval=5)
    assert t.call(1000, "a") == ["a"]
    assert t.call(1004, "b") == []


def test_the_interval_runs_from_the_last_run_not_the_last_call():
    t = Throttler(interval=10, trailing=False)
    assert t.call(0, "a") == ["a"]
    for now in (3, 6, 9):
        assert t.call(now, "x") == []
    assert t.call(10, "b") == ["b"]


def test_none_is_a_value():
    t = Throttler(interval=1)
    assert t.call(0) == [None]
    assert t.call(1) == [None]


def test_a_larger_gap_between_runs():
    t = Throttler(interval=3)
    assert t.call(0, 1) == [1]
    assert t.call(100, 2) == [2]
    assert t.call(101, 3) == []
