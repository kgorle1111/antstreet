import pytest
from elevator import Elevator


def test_new_car_is_at_the_start_and_idle():
    e = Elevator(10, start=4)
    assert e.floor == 4
    assert e.direction == "idle"
    assert e.pending() == []


def test_start_defaults_to_the_ground_floor():
    assert Elevator(5).floor == 0


@pytest.mark.parametrize("floors", [1, 0, -3, 2.5, "4"])
def test_floors_must_be_a_whole_number_of_at_least_two(floors):
    with pytest.raises(ValueError):
        Elevator(floors)


@pytest.mark.parametrize("start", [-1, 5, 99, 1.5])
def test_start_must_be_a_floor_of_the_building(start):
    with pytest.raises(ValueError):
        Elevator(5, start=start)


def test_smallest_and_largest_valid_starts():
    assert Elevator(5, start=0).floor == 0
    assert Elevator(5, start=4).floor == 4
    assert Elevator(2).floor == 0


def test_pending_returns_a_new_list():
    e = Elevator(5)
    e.request(3)
    e.pending().append(99)
    assert e.pending() == [3]
