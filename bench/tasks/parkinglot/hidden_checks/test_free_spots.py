from parkinglot import ParkingLot


def test_a_new_lot_is_entirely_free():
    assert ParkingLot(2, 1, 3).free_spots() == {"small": 2, "medium": 1, "large": 3}


def test_sizes_with_no_spots_report_zero():
    assert ParkingLot(large=2).free_spots() == {"small": 0, "medium": 0, "large": 2}


def test_free_spots_follow_the_size_of_the_spot_taken_not_the_kind():
    lot = ParkingLot(1, 1, 1)
    lot.park("m", "motorcycle", 0)
    assert lot.free_spots() == {"small": 0, "medium": 1, "large": 1}
    lot.park("m2", "motorcycle", 0)
    assert lot.free_spots() == {"small": 0, "medium": 0, "large": 1}
    lot.park("c", "car", 0)
    assert lot.free_spots() == {"small": 0, "medium": 0, "large": 0}


def test_leaving_frees_the_spot_again():
    lot = ParkingLot(1, 1, 1)
    lot.park("c", "car", 0)
    lot.park("c2", "car", 0)
    assert lot.free_spots() == {"small": 1, "medium": 0, "large": 0}
    lot.leave("c", 10)
    assert lot.free_spots() == {"small": 1, "medium": 1, "large": 0}


def test_free_spots_is_a_new_dict_each_time():
    lot = ParkingLot(small=2)
    free = lot.free_spots()
    free["small"] = 99
    assert lot.free_spots() == {"small": 2, "medium": 0, "large": 0}
