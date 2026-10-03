import pytest
from parkinglot import ParkingLot


def stay(seconds, kind="truck"):
    lot = ParkingLot(small=1, medium=1, large=1)
    lot.park("p", kind, 0.0)
    return lot.leave("p", float(seconds))


def test_eight_hours_is_charged_as_eight():
    assert stay(8 * 3600) == 400 * 8


def test_a_started_ninth_hour_is_not_charged():
    assert stay(8 * 3600 + 1) == 400 * 8


@pytest.mark.parametrize("seconds", [9 * 3600, 24 * 3600, 30 * 24 * 3600])
def test_longer_stays_stay_at_the_cap(seconds):
    assert stay(seconds) == 400 * 8


def test_seven_hours_and_a_bit_is_eight_hours():
    assert stay(7 * 3600 + 1) == 400 * 8


def test_cap_is_in_hours_so_it_scales_with_the_rate():
    assert stay(100 * 3600, kind="motorcycle") == 100 * 8
    assert stay(100 * 3600, kind="car") == 200 * 8
