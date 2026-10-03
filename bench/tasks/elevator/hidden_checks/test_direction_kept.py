from elevator import Elevator


def run(e, limit=100):
    served, ticks = [], 0
    while e.pending() and ticks < limit:
        got = e.step()
        ticks += 1
        if got is not None:
            served.append(got)
    return served, ticks


def test_going_up_the_car_does_not_turn_for_a_nearer_floor_below():
    e = Elevator(10)
    e.request(8)
    for _ in range(4):
        assert e.step() is None
    assert (e.floor, e.direction) == (4, "up")
    e.request(2)
    served, ticks = run(e)
    assert served == [8, 2]
    assert ticks == 12
    assert e.floor == 2


def test_going_down_the_car_does_not_turn_for_a_nearer_floor_above():
    e = Elevator(10, start=9)
    e.request(0)
    for _ in range(4):
        assert e.step() is None
    assert (e.floor, e.direction) == (5, "down")
    e.request(8)
    served, ticks = run(e)
    assert served == [0, 8]
    assert ticks == 15
    assert e.floor == 8


def test_a_request_just_behind_the_car_waits_for_the_sweep():
    e = Elevator(10, start=0)
    e.request(9)
    e.step()
    e.step()
    e.request(1)
    served, _ = run(e)
    assert served == [9, 1]
