Create a Python module `elevator.py` (standard library only) with one class:

    Elevator(floors: int, start: int = 0)

    request(floor: int) -> None
    step() -> int | None
    floor -> int                 # property: the floor the car is at
    direction -> str             # property: "up", "down" or "idle"
    pending() -> list[int]

It simulates one elevator car, one tick at a time. There is no clock and no door model. Floors
are numbered `0` to `floors - 1`.

1. `floors` must be a whole number of at least 2 and `start` a whole number from 0 to
   `floors - 1`; otherwise the constructor raises `ValueError`. The car starts at `start` with
   direction `"idle"` and no requests.
2. `request(floor)` adds `floor` to the set of floors the car must stop at. A `floor` that is not a
   whole number from 0 to `floors - 1` raises `ValueError` and changes nothing. Requesting a floor
   that is already pending changes nothing. Requesting the floor the car is at is allowed.
   `pending()` returns a new list of the pending floors in ascending order.
3. Each call to `step()` is one tick and does exactly one of these, checked in this order:
   a. If nothing is pending: nothing happens; the direction is set to `"idle"`; it returns `None`.
   b. If the car's current floor is pending: the car stays where it is, serves that floor (it is
      no longer pending) and `step()` returns that floor number. If nothing is pending any more,
      the direction becomes `"idle"`; otherwise the direction is unchanged.
   c. Otherwise the car moves one floor and `step()` returns `None`. It moves in its current
      direction if that direction is `"up"` and some pending floor is above the car, or `"down"`
      and some pending floor is below it. If not (the direction is `"idle"`, or nothing is pending
      ahead in the current direction) it moves towards the nearest pending floor, nearest meaning
      the smallest distance in floors; when two pending floors are equally near it goes up. The
      direction becomes the direction it moved in.
4. A floor the car passes while it is pending is therefore served on the way, one tick after the
   car arrives at it, and the car does not turn round while a pending floor is still ahead of it
   in its current direction, however near a pending floor behind it is.
