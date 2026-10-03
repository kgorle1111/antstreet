import pytest
from parkinglot import ParkingLot


def test_no_free_spot_returns_none():
    lot = ParkingLot(small=1, large=1)
    assert lot.park("m1", "motorcycle", 0) == 1
    assert lot.park("t", "truck", 0) == 2
    assert lot.park("m2", "motorcycle", 0) is None
    assert lot.free_spots() == {"small": 0, "medium": 0, "large": 0}


def test_free_small_spots_do_not_help_a_car_or_a_truck():
    lot = ParkingLot(small=3, large=1)
    assert lot.park("t1", "truck", 0) == 4
    assert lot.park("t2", "truck", 0) is None
    assert lot.park("c", "car", 0) is None
    assert lot.free_spots()["small"] == 3


def test_a_failed_park_does_not_register_the_plate():
    lot = ParkingLot(large=1)
    lot.park("t1", "truck", 0)
    assert lot.park("t2", "truck", 0) is None
    assert lot.spot_of("t2") is None
    lot.leave("t1", 10)
    assert lot.park("t2", "truck", 10) == 1


def test_a_failed_park_for_a_plate_that_cannot_leave():
    lot = ParkingLot(large=1)
    lot.park("t1", "truck", 0)
    assert lot.park("t2", "truck", 0) is None
    with pytest.raises(KeyError):
        lot.leave("t2", 5)


def test_a_full_lot_still_parks_a_smaller_kind_that_fits_elsewhere():
    lot = ParkingLot(small=1, medium=1, large=1)
    lot.park("t", "truck", 0)
    lot.park("c", "car", 0)
    assert lot.park("c2", "car", 0) is None
    assert lot.park("m", "motorcycle", 0) == 1
