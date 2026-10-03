from parkinglot import ParkingLot


def test_the_lowest_numbered_free_spot_is_used():
    lot = ParkingLot(small=3)
    assert [lot.park(p, "motorcycle", 0) for p in "abc"] == [1, 2, 3]
    lot.leave("b", 10)
    assert lot.park("d", "motorcycle", 20) == 2


def test_spots_are_reused_in_ascending_order():
    lot = ParkingLot(small=3)
    for p in "abc":
        lot.park(p, "motorcycle", 0)
    lot.leave("c", 10)
    lot.leave("a", 10)
    assert lot.park("d", "motorcycle", 20) == 1
    assert lot.park("e", "motorcycle", 20) == 3
    assert lot.park("f", "motorcycle", 20) is None


def test_the_lowest_number_is_taken_within_the_chosen_size_not_overall():
    lot = ParkingLot(2, 2, 0)
    assert lot.park("a", "motorcycle", 0) == 1
    assert lot.park("b", "motorcycle", 0) == 2
    assert lot.park("c", "motorcycle", 0) == 3
    lot.leave("a", 10)
    assert lot.park("d", "car", 20) == 4
    assert lot.park("e", "motorcycle", 20) == 1


def test_a_spot_is_free_again_as_soon_as_the_vehicle_leaves():
    lot = ParkingLot(large=1)
    assert lot.park("a", "truck", 0) == 1
    assert lot.park("b", "truck", 0) is None
    lot.leave("a", 5)
    assert lot.park("b", "truck", 5) == 1


def test_a_plate_can_park_again_after_leaving():
    lot = ParkingLot(small=2)
    assert lot.park("a", "motorcycle", 0) == 1
    lot.leave("a", 100)
    assert lot.park("b", "motorcycle", 100) == 1
    assert lot.park("a", "motorcycle", 200) == 2
    assert lot.spot_of("a") == 2
