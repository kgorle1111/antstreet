from elevator import Elevator


def test_step_with_nothing_pending_changes_nothing():
    e = Elevator(10, start=3)
    assert e.step() is None
    assert e.step() is None
    assert (e.floor, e.direction) == (3, "idle")


def test_direction_is_idle_again_once_the_last_request_is_served():
    e = Elevator(10)
    e.request(2)
    for _ in range(2):
        e.step()
    assert e.direction == "up"
    assert e.step() == 2
    assert e.direction == "idle"
    assert e.step() is None
    assert e.direction == "idle"


def test_direction_is_not_idle_while_requests_remain_after_a_stop():
    e = Elevator(10)
    e.request(2)
    e.request(6)
    for _ in range(3):
        e.step()
    assert e.pending() == [6]
    assert e.direction == "up"


def test_idle_car_stays_put_and_resumes_on_a_new_request():
    e = Elevator(10, start=7)
    for _ in range(5):
        e.step()
    assert e.floor == 7
    e.request(4)
    e.step()
    assert (e.floor, e.direction) == (6, "down")
