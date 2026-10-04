import pytest
from elevator import Elevator


def test_pending_is_sorted_ascending():
    e = Elevator(10)
    for f in (7, 2, 9, 4):
        e.request(f)
    assert e.pending() == [2, 4, 7, 9]


def test_duplicate_requests_are_one_request():
    e = Elevator(10)
    e.request(5)
    e.request(5)
    e.request(5)
    assert e.pending() == [5]


def test_a_duplicate_is_served_once():
    e = Elevator(10, start=3)
    e.request(4)
    e.request(4)
    served = [e.step() for _ in range(6)]
    assert served == [None, 4, None, None, None, None]
    assert e.pending() == []
    assert e.floor == 4


@pytest.mark.parametrize("floor", [-1, 10, 11, 1.5, "3", None])
def test_bad_floor_raises_and_changes_nothing(floor):
    e = Elevator(10)
    e.request(6)
    with pytest.raises(ValueError):
        e.request(floor)
    assert e.pending() == [6]


def test_first_and_last_floor_are_valid():
    e = Elevator(10)
    e.request(0)
    e.request(9)
    assert e.pending() == [0, 9]


def test_request_returns_none():
    assert Elevator(3).request(1) is None
