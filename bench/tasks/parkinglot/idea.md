Create a Python module `parkinglot.py` (standard library only) with one class:

    ParkingLot(small: int = 0, medium: int = 0, large: int = 0)

    park(plate: str, kind: str, now: float) -> int | None
    leave(plate: str, now: float) -> int
    free_spots() -> dict[str, int]
    spot_of(plate: str) -> int | None

It is a parking lot with numbered spots of three sizes. It never reads a clock: `now` is the time
in seconds given by the caller. Money is whole cents.

1. `small`, `medium` and `large` are how many spots of each size the lot has: whole numbers of at
   least 0, and at least one spot in all. Otherwise the constructor raises `ValueError`. Spots are
   numbered from 1: the small spots first, then the medium ones, then the large ones. For
   `ParkingLot(2, 1, 3)` spots 1-2 are small, 3 is medium and 4-6 are large.
2. A vehicle has a `kind`: `"motorcycle"` fits a spot of any size, `"car"` fits a medium or large
   spot, `"truck"` fits only a large spot.
3. `park(plate, kind, now)` parks the vehicle in the smallest size of spot that fits it and has a free
   spot, and in that size the free spot with the lowest number. It records `now` as the time the
   vehicle came in and returns the spot number. When no fitting spot is free it returns `None` and
   the vehicle is not parked. A spot is free again as soon as its vehicle has left.
   `ValueError` is raised, and nothing changes, for a `plate` that is not a non-empty `str`, for a
   `kind` that is not one of the three above, and for a `plate` that is already parked.
4. `leave(plate, now)` removes the vehicle, frees its spot and returns the fee in cents. A plate that
   is not parked raises `KeyError`. A `now` earlier than the time the vehicle came in raises
   `ValueError` and the vehicle stays parked.
5. The fee depends on the stay `d = now - came_in` in seconds and on the size of the spot the
   vehicle occupied, not on its kind. The rate per hour is 100 for a small spot, 200 for a
   medium one and 400 for a large one. A stay of up to and including 900 seconds is free. A longer stay
   is charged per started hour: `ceil(d / 3600)` hours (3600 seconds exactly is 1 hour, 3601 is 2),
   but at most 8 hours are charged, however long the stay. The fee is the rate times the charged
   hours.
6. `free_spots()` returns a new dict with the keys `"small"`, `"medium"` and `"large"` giving the
   number of free spots of each size (0 included). `spot_of(plate)` returns the spot number the
   plate is parked in, or `None` if it is not parked.
