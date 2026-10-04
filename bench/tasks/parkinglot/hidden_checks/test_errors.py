import pytest
from parkinglot import ParkingLot


def test_unknown_kind_raises_and_parks_nothing():
    lot = ParkingLot(small=1)
    with pytest.raises(ValueError):
        lot.park("a", "bus", 0)
    assert lot.spot_of("a") is None
    assert lot.free_spots()["small"] == 1


@pytest.mark.parametrize("plate", ["", None, 5])
def test_bad_plate_raises(plate):
    lot = ParkingLot(small=1)
    with pytest.raises(ValueError):
        lot.park(plate, "motorcycle", 0)
    assert lot.free_spots()["small"] == 1


def test_parking_a_plate_twice_raises_and_keeps_the_first_entry():
    lot = ParkingLot(small=2)
    assert lot.park("a", "motorcycle", 0) == 1
    with pytest.raises(ValueError):
        lot.park("a", "motorcycle", 5000)
    assert lot.spot_of("a") == 1
    assert lot.free_spots()["small"] == 1
    assert lot.leave("a", 3600) == 100


def test_the_same_plate_cannot_be_parked_as_another_kind_either():
    lot = ParkingLot(1, 1, 1)
    lot.park("a", "motorcycle", 0)
    with pytest.raises(ValueError):
        lot.park("a", "truck", 0)


def test_leaving_an_unknown_plate_raises_key_error():
    lot = ParkingLot(small=1)
    with pytest.raises(KeyError):
        lot.leave("ghost", 10)


def test_leaving_twice_raises_key_error():
    lot = ParkingLot(small=1)
    lot.park("a", "motorcycle", 0)
    lot.leave("a", 10)
    with pytest.raises(KeyError):
        lot.leave("a", 20)


def test_leaving_before_arriving_raises_and_keeps_the_vehicle():
    lot = ParkingLot(small=1)
    lot.park("a", "motorcycle", 100)
    with pytest.raises(ValueError):
        lot.leave("a", 99)
    assert lot.spot_of("a") == 1
    assert lot.free_spots()["small"] == 0
    assert lot.leave("a", 100) == 0


@pytest.mark.parametrize(
    "counts",
    [(0, 0, 0), (-1, 1, 1), (1, -1, 1), (1, 1, -1), (1.5, 1, 1), ("2", 1, 1), (None, 1, 1)],
)
def test_bad_counts_raise(counts):
    with pytest.raises(ValueError):
        ParkingLot(*counts)


def test_default_arguments_need_at_least_one_spot():
    with pytest.raises(ValueError):
        ParkingLot()
    ParkingLot(small=1)
    ParkingLot(medium=1)
    ParkingLot(large=1)
