from elevator import Elevator


def run(e, limit=100):
    served, ticks = [], 0
    while e.pending() and ticks < limit:
        got = e.step()
        ticks += 1
        if got is not None:
            served.append(got)
    return served, ticks


def test_idle_car_heads_for_the_nearest_floor_even_if_it_is_below():
    e = Elevator(10, start=5)
    e.request(2)
    e.request(9)
    served, ticks = run(e)
    assert served == [2, 9]
    assert ticks == 12


def test_idle_car_heads_for_the_nearest_floor_even_if_it_is_above():
    e = Elevator(10, start=5)
    e.request(8)
    e.request(0)
    served, ticks = run(e)
    assert served == [8, 0]
    assert ticks == 3 + 1 + 8 + 1


def test_a_tie_goes_up():
    e = Elevator(10, start=5)
    e.request(3)
    e.request(7)
    served, ticks = run(e)
    assert served == [7, 3]
    assert ticks == 8


def test_first_move_sets_the_direction_from_the_nearest_floor():
    e = Elevator(10, start=5)
    e.request(4)
    e.request(9)
    e.step()
    assert (e.floor, e.direction) == (4, "down")


def test_tie_with_three_floors_picks_the_higher_of_the_equally_near():
    e = Elevator(10, start=5)
    e.request(4)
    e.request(6)
    e.request(0)
    e.step()
    assert (e.floor, e.direction) == (6, "up")
