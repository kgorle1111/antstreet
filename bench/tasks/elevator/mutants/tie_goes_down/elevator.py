# When two pending floors are equally near the car goes down instead of up.
class Elevator:
    def __init__(self, floors: int, start: int = 0) -> None:
        if type(floors) is not int or floors < 2:
            raise ValueError("floors must be a whole number of at least 2")
        if type(start) is not int or not 0 <= start < floors:
            raise ValueError("start must be a floor of the building")
        self._floors = floors
        self._floor = start
        self._direction = "idle"
        self._pending: set[int] = set()

    @property
    def floor(self) -> int:
        return self._floor

    @property
    def direction(self) -> str:
        return self._direction

    def request(self, floor: int) -> None:
        if type(floor) is not int or not 0 <= floor < self._floors:
            raise ValueError(f"no such floor: {floor!r}")
        self._pending.add(floor)

    def pending(self) -> list[int]:
        return sorted(self._pending)

    def step(self) -> int | None:
        if not self._pending:
            self._direction = "idle"
            return None
        if self._floor in self._pending:
            self._pending.remove(self._floor)
            if not self._pending:
                self._direction = "idle"
            return self._floor
        above = any(p > self._floor for p in self._pending)
        below = any(p < self._floor for p in self._pending)
        if self._direction == "up" and above:
            move = 1
        elif self._direction == "down" and below:
            move = -1
        else:
            # nearest first; on a tie the higher floor wins, i.e. the car goes up
            nearest = min(self._pending, key=lambda p: (abs(p - self._floor), p))
            move = 1 if nearest > self._floor else -1
        self._floor += move
        self._direction = "up" if move == 1 else "down"
        return None
