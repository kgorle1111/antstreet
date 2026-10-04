import pytest
from parkinglot import ParkingLot


def stay(seconds, kind="car"):
    lot = ParkingLot(small=1, medium=1, large=1)
    lot.park("p", kind, 10000.0)
    return lot.leave("p", 10000.0 + seconds)


@pytest.mark.parametrize(
    "seconds,hours",
    [
        (901, 1),
        (1800, 1),
        (3599, 1),
        (3600, 1),
        (3601, 2),
        (7199, 2),
        (7200, 2),
        (7200.5, 3),
        (10800, 3),
        (10801, 4),
        (18000, 5),
    ],
)
def test_started_hours_are_charged_in_full(seconds, hours):
    assert stay(seconds) == 200 * hours


def test_the_stay_is_measured_from_the_arrival_time():
    lot = ParkingLot(small=2)
    lot.park("a", "motorcycle", 1000)
    lot.park("b", "motorcycle", 4000)
    assert lot.leave("a", 4600) == 100
    assert lot.leave("b", 4600) == 0
    lot.park("c", "motorcycle", 5000)
    assert lot.leave("c", 8600) == 100
