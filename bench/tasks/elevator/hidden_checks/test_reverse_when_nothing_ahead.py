from elevator import Elevator


def test_car_turns_round_after_the_last_floor_ahead():
    e = Elevator(10, start=5)
    e.request(8)
    e.request(1)
    served, directions = [], []
    for _ in range(12):
        got = e.step()
        directions.append(e.direction)
        if got is not None:
            served.append(got)
    assert served == [8, 1]
    assert directions[:3] == ["up", "up", "up"]
    assert directions[3] == "up"
    assert directions[4] == "down"
    assert directions[-1] == "idle"
    assert e.floor == 1


def test_serving_with_requests_left_keeps_the_direction_unchanged():
    e = Elevator(10, start=5)
    e.request(7)
    e.request(2)
    for _ in range(2):
        e.step()
    assert e.step() == 7
    assert e.direction == "up"
    e.step()
    assert (e.floor, e.direction) == (6, "down")


def test_turning_round_with_only_one_floor_behind():
    e = Elevator(10, start=0)
    e.request(6)
    for _ in range(7):
        e.step()
    e.request(3)
    assert e.pending() == [3]
    assert e.direction == "idle"
    e.step()
    assert (e.floor, e.direction) == (5, "down")
