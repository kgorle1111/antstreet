def _int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, got {value!r}")
    return value


def _validate(items: object, capacity: object) -> list[tuple[int, int]]:
    if not isinstance(items, list | tuple):
        raise TypeError("items must be a list of (weight, value) pairs")
    checked = []
    for item in items:
        if not isinstance(item, list | tuple) or len(item) != 2:
            raise ValueError(f"an item must be a (weight, value) pair, got {item!r}")
        weight, value = _int(item[0], "a weight"), _int(item[1], "a value")
        if weight < 1:
            raise ValueError(f"a weight must be at least 1, got {weight}")
        if value < 0:
            raise ValueError(f"a value must not be negative, got {value}")
        checked.append((weight, value))
    if _int(capacity, "the capacity") < 0:
        raise ValueError(f"the capacity must not be negative, got {capacity}")
    return checked


def knapsack(items: list[tuple[int, int]], capacity: int) -> tuple[int, list[int]]:
    checked = _validate(items, capacity)
    n = len(checked)
    # best[i][c] is (value, -weight) of the best choice from items i.. with room c.
    best = [[(0, 0)] * (capacity + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        weight, value = checked[i]
        for room in range(capacity + 1):
            skip = best[i + 1][room]
            if weight <= room:
                got_value, got_neg_weight = best[i + 1][room - weight]
                take = (got_value + value, got_neg_weight - weight)
                best[i][room] = take if take >= skip else skip
            else:
                best[i][room] = skip
    chosen: list[int] = []
    room = capacity
    for i, (weight, value) in enumerate(checked):
        if weight <= room:
            got_value, got_neg_weight = best[i + 1][room - weight]
            if (got_value + value, got_neg_weight - weight) == best[i][room]:
                chosen.append(i)
                room -= weight
    return best[0][capacity][0], chosen
