from elevator import Elevator


def test_every_pending_floor_on_the_way_is_served_in_order():
    e = Elevator(10)
    for f in (8, 2, 5):
        e.request(f)
    got = [e.step() for _ in range(11)]
    assert got == [None, None, 2, None, None, None, 5, None, None, None, 8]
    assert e.pending() == []
    assert e.floor == 8


def test_floors_going_down_are_served_in_descending_order():
    e = Elevator(10, start=9)
    for f in (1, 6, 4):
        e.request(f)
    served = []
    for _ in range(30):
        got = e.step()
        if got is not None:
            served.append(got)
    assert served == [6, 4, 1]


def test_request_made_ahead_of_the_car_is_served_on_the_way():
    e = Elevator(10)
    e.request(9)
    for _ in range(3):
        e.step()
    e.request(5)
    served = []
    for _ in range(10):
        got = e.step()
        if got is not None:
            served.append(got)
    assert served == [5, 9]
