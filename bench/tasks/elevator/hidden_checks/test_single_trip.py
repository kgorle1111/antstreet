from elevator import Elevator


def test_going_up_takes_one_tick_per_floor_then_one_to_serve():
    e = Elevator(10)
    e.request(3)
    assert [e.step() for _ in range(4)] == [None, None, None, 3]
    assert e.floor == 3
    assert e.pending() == []


def test_floor_and_direction_while_moving_up():
    e = Elevator(10)
    e.request(3)
    e.step()
    assert (e.floor, e.direction) == (1, "up")
    e.step()
    assert (e.floor, e.direction) == (2, "up")
    e.step()
    assert (e.floor, e.direction) == (3, "up")
    assert e.step() == 3
    assert (e.floor, e.direction) == (3, "idle")


def test_going_down():
    e = Elevator(6, start=5)
    e.request(1)
    assert [e.step() for _ in range(5)] == [None, None, None, None, 1]
    assert e.floor == 1


def test_direction_while_moving_down():
    e = Elevator(6, start=5)
    e.request(1)
    e.step()
    assert (e.floor, e.direction) == (4, "down")


def test_a_second_trip_after_the_first():
    e = Elevator(10)
    e.request(2)
    for _ in range(3):
        e.step()
    e.request(0)
    assert [e.step() for _ in range(3)] == [None, None, 0]
    assert e.floor == 0
