from parkinglot import ParkingLot


def test_motorcycles_take_the_smallest_spots_first_then_larger_ones():
    lot = ParkingLot(2, 2, 2)
    got = [lot.park(f"m{i}", "motorcycle", 0) for i in range(7)]
    assert got == [1, 2, 3, 4, 5, 6, None]


def test_cars_skip_small_spots():
    lot = ParkingLot(2, 2, 2)
    got = [lot.park(f"c{i}", "car", 0) for i in range(5)]
    assert got == [3, 4, 5, 6, None]


def test_trucks_only_use_large_spots():
    lot = ParkingLot(2, 2, 2)
    got = [lot.park(f"t{i}", "truck", 0) for i in range(3)]
    assert got == [5, 6, None]


def test_mixed_vehicles_each_take_the_smallest_fitting_size():
    lot = ParkingLot(2, 2, 2)
    assert lot.park("car", "car", 0) == 3
    assert lot.park("moto1", "motorcycle", 0) == 1
    assert lot.park("truck", "truck", 0) == 5
    assert lot.park("moto2", "motorcycle", 0) == 2
    assert lot.park("moto3", "motorcycle", 0) == 4


def test_a_missing_size_is_skipped():
    lot = ParkingLot(small=1, large=1)
    assert lot.park("car", "car", 0) == 2
    assert lot.park("moto", "motorcycle", 0) == 1


def test_numbering_follows_the_documented_example():
    lot = ParkingLot(2, 1, 3)
    assert [lot.park(f"m{i}", "motorcycle", 0) for i in range(6)] == [1, 2, 3, 4, 5, 6]
    lot = ParkingLot(2, 1, 3)
    assert lot.park("c", "car", 0) == 3
    assert lot.park("t", "truck", 0) == 4


def test_only_medium_spots_take_a_motorcycle_and_a_car_but_no_truck():
    lot = ParkingLot(medium=1)
    assert lot.park("t", "truck", 0) is None
    assert lot.park("m", "motorcycle", 0) == 1


def test_spot_of_reports_where_each_plate_is():
    lot = ParkingLot(1, 1, 1)
    lot.park("a", "car", 0)
    lot.park("b", "motorcycle", 0)
    assert lot.spot_of("a") == 2
    assert lot.spot_of("b") == 1
    assert lot.spot_of("nobody") is None
