import pytest
from parkinglot import ParkingLot


def stay(seconds, kind="motorcycle", lot=None):
    lot = lot or ParkingLot(small=1, medium=1, large=1)
    lot.park("p", kind, 5000.0)
    return lot.leave("p", 5000.0 + seconds)


@pytest.mark.parametrize("kind", ["motorcycle", "car", "truck"])
@pytest.mark.parametrize("seconds", [0, 1, 899, 900])
def test_up_to_fifteen_minutes_is_free(kind, seconds):
    assert stay(seconds, kind) == 0


def test_just_over_fifteen_minutes_costs_one_hour():
    assert stay(901) == 100
    assert stay(900.5) == 100


def test_the_fee_is_an_int():
    assert isinstance(stay(1000), int)
    assert isinstance(stay(10), int)


def test_the_grace_period_is_per_stay_not_per_plate():
    lot = ParkingLot(small=1)
    lot.park("p", "motorcycle", 0)
    assert lot.leave("p", 900) == 0
    lot.park("p", "motorcycle", 1000)
    assert lot.leave("p", 2000) == 100
