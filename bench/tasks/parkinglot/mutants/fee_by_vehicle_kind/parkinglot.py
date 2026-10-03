# The rate follows the vehicle kind instead of the size of the spot it occupies.
import math

SIZES = ("small", "medium", "large")
FITS = {
    "motorcycle": ("small", "medium", "large"),
    "car": ("medium", "large"),
    "truck": ("large",),
}
RATE = {"small": 100, "medium": 200, "large": 400}  # cents per hour
GRACE_S = 900
HOUR_S = 3600
MAX_HOURS = 8


class ParkingLot:
    def __init__(self, small: int = 0, medium: int = 0, large: int = 0) -> None:
        counts = (small, medium, large)
        if any(type(c) is not int or c < 0 for c in counts) or sum(counts) < 1:
            raise ValueError("counts must be whole numbers of at least 0, with at least one spot")
        self._size_of: dict[int, str] = {}
        number = 0
        for size, count in zip(SIZES, counts, strict=True):
            for _ in range(count):
                number += 1
                self._size_of[number] = size
        self._parked: dict[str, tuple[int, float]] = {}  # plate -> (spot, time in)
        self._kinds: dict[str, str] = {}

    def park(self, plate: str, kind: str, now: float) -> int | None:
        if type(plate) is not str or not plate:
            raise ValueError("plate must be a non-empty string")
        if kind not in FITS:
            raise ValueError(f"unknown kind {kind!r}")
        if plate in self._parked:
            raise ValueError(f"{plate!r} is already parked")
        taken = {spot for spot, _ in self._parked.values()}
        for size in FITS[kind]:
            for spot in sorted(self._size_of):
                if self._size_of[spot] == size and spot not in taken:
                    self._parked[plate] = (spot, now)
                    self._kinds[plate] = kind
                    return spot
        return None

    def leave(self, plate: str, now: float) -> int:
        if plate not in self._parked:
            raise KeyError(plate)
        spot, came_in = self._parked[plate]
        if now < came_in:
            raise ValueError("cannot leave before arriving")
        del self._parked[plate]
        stay = now - came_in
        if stay <= GRACE_S:
            return 0
        hours = min(math.ceil(stay / HOUR_S), MAX_HOURS)
        return RATE[FITS[self._kinds[plate]][0]] * hours

    def free_spots(self) -> dict[str, int]:
        taken = {spot for spot, _ in self._parked.values()}
        free = dict.fromkeys(SIZES, 0)
        for spot, size in self._size_of.items():
            if spot not in taken:
                free[size] += 1
        return free

    def spot_of(self, plate: str) -> int | None:
        return self._parked[plate][0] if plate in self._parked else None
