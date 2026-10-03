from elevator import Elevator


def test_request_for_the_current_floor_is_served_without_moving():
    e = Elevator(5, start=2)
    e.request(2)
    assert e.pending() == [2]
    assert e.step() == 2
    assert e.floor == 2
    assert e.pending() == []
    assert e.direction == "idle"


def test_current_floor_is_served_before_the_car_moves_on():
    e = Elevator(10)
    e.request(8)
    for _ in range(4):
        e.step()
    e.request(4)
    assert e.step() == 4
    assert (e.floor, e.direction) == (4, "up")
    assert e.step() is None
    assert e.floor == 5


def test_current_floor_and_another_floor():
    e = Elevator(10, start=3)
    e.request(3)
    e.request(6)
    assert e.step() == 3
    assert e.floor == 3
    assert e.direction == "idle"
    assert [e.step() for _ in range(4)] == [None, None, None, 6]


def test_serving_takes_the_tick_even_when_the_car_just_arrived():
    e = Elevator(3)
    e.request(1)
    assert e.step() is None
    assert e.floor == 1
    assert e.pending() == [1]
    assert e.step() == 1
