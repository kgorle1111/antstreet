from parkinglot import ParkingLot


def test_rates_per_hour_by_spot_size():
    lot = ParkingLot(1, 1, 1)
    assert lot.park("s", "motorcycle", 0) == 1
    assert lot.park("m", "car", 0) == 2
    assert lot.park("l", "truck", 0) == 3
    assert lot.leave("s", 3600) == 100
    assert lot.leave("m", 3600) == 200
    assert lot.leave("l", 3600) == 400


def test_a_motorcycle_in_a_medium_spot_pays_the_medium_rate():
    lot = ParkingLot(medium=1, large=1)
    assert lot.park("m", "motorcycle", 0) == 1
    assert lot.leave("m", 3600) == 200


def test_a_motorcycle_in_a_large_spot_pays_the_large_rate():
    lot = ParkingLot(large=1)
    assert lot.park("m", "motorcycle", 0) == 1
    assert lot.leave("m", 3600) == 400


def test_a_car_in_a_large_spot_pays_the_large_rate():
    lot = ParkingLot(large=1)
    assert lot.park("c", "car", 0) == 1
    assert lot.leave("c", 7200) == 800


def test_a_car_pushed_up_to_a_large_spot_by_a_full_medium_row():
    lot = ParkingLot(medium=1, large=1)
    lot.park("c1", "car", 0)
    assert lot.park("c2", "car", 0) == 2
    assert lot.leave("c1", 3600) == 200
    assert lot.leave("c2", 3600) == 400


def test_the_rate_follows_the_spot_after_it_is_reused():
    lot = ParkingLot(1, 0, 1)
    lot.park("a", "motorcycle", 0)
    lot.park("b", "motorcycle", 0)
    lot.leave("a", 3600)
    lot.park("c", "motorcycle", 4000)
    assert lot.leave("c", 4000 + 3600) == 100
    assert lot.leave("b", 3600) == 400
