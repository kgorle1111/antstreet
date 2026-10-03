# Items are taken in order of value per weight while they fit, which is not always the best choice.
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
    order = sorted(range(len(checked)), key=lambda i: (-checked[i][1] / checked[i][0], i))
    room, total, chosen = capacity, 0, []
    for i in order:
        weight, value = checked[i]
        if value > 0 and weight <= room:
            chosen.append(i)
            room -= weight
            total += value
    return total, sorted(chosen)
